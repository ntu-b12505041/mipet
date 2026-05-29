"""Food object detection using TensorFlow Lite SSD-style models."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Optional, Sequence, Tuple

from .config import FoodDetectionConfig


@dataclass(frozen=True)
class FoodDetectionResult:
    detected: bool
    label: str = ""
    score: float = 0.0
    bounding_box: Optional[Tuple[int, int, int, int]] = None
    target_labels: Tuple[str, ...] = ()
    raw_label: str = ""


def _require_cv2():
    try:
        import cv2
    except ImportError as exc:
        raise RuntimeError("OpenCV is required for food detection.") from exc
    return cv2


def _load_interpreter(model_path: str):
    try:
        from tflite_runtime.interpreter import Interpreter
    except ImportError:
        try:
            from ai_edge_litert.interpreter import Interpreter
        except ImportError:
            try:
                from tensorflow.lite.python.interpreter import Interpreter
            except ImportError as exc:
                raise RuntimeError(
                    "TensorFlow Lite runtime is required. Install tflite_runtime, ai-edge-litert, or tensorflow."
                ) from exc
    return Interpreter(model_path=model_path)


def _normalize_label(label: str) -> str:
    return label.strip().lower().replace("_", " ")


def load_labels(labels_path: str) -> Tuple[str, ...]:
    labels = []
    for raw_line in Path(labels_path).read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        parts = line.split(maxsplit=1)
        if len(parts) == 2 and parts[0].isdigit():
            line = parts[1].strip()
        labels.append(line)
    return tuple(labels)


class FoodDetector:
    """TFLite detector wrapper for COCO food-like object classes.

    This expects SSD MobileNet style TFLite outputs: boxes, classes, scores,
    and optional detection count.
    """

    def __init__(self, config: Optional[FoodDetectionConfig] = None) -> None:
        self.config = config or FoodDetectionConfig()
        self.enabled = bool(self.config.model_path and self.config.labels_path)
        self.labels: Tuple[str, ...] = ()
        self._interpreter = None
        self._input_details = None
        self._output_details = None
        self._input_height = 0
        self._input_width = 0
        self._input_dtype = None

        if not self.enabled:
            return

        self.labels = load_labels(self.config.labels_path)
        self._interpreter = _load_interpreter(self.config.model_path)
        self._interpreter.allocate_tensors()
        self._input_details = self._interpreter.get_input_details()
        self._output_details = self._interpreter.get_output_details()

        input_shape = self._input_details[0]["shape"]
        self._input_height = int(input_shape[1])
        self._input_width = int(input_shape[2])
        self._input_dtype = self._input_details[0]["dtype"]

    def detect(self, frame) -> FoodDetectionResult:
        if not self.enabled:
            return FoodDetectionResult(detected=False, target_labels=self.config.target_labels)

        cv2 = _require_cv2()
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        resized = cv2.resize(rgb, (self._input_width, self._input_height))
        input_data = resized.reshape((1, self._input_height, self._input_width, 3))

        if str(self._input_dtype) == "float32":
            input_data = input_data.astype("float32")
            input_data = (input_data - self.config.input_mean) / self.config.input_std

        self._interpreter.set_tensor(self._input_details[0]["index"], input_data)
        self._interpreter.invoke()
        outputs = [
            self._interpreter.get_tensor(detail["index"])
            for detail in self._output_details
        ]

        boxes, classes, scores, count = self._parse_ssd_outputs(outputs)
        frame_height, frame_width = frame.shape[:2]
        target_labels = {_normalize_label(label) for label in self.config.target_labels}

        best_result = FoodDetectionResult(detected=False, target_labels=self.config.target_labels)
        best_score = -1.0
        detection_count = min(count, len(scores), len(classes), len(boxes))

        for index in range(detection_count):
            score = float(scores[index])
            if score < self.config.score_threshold:
                continue

            class_id = int(classes[index])
            label = self._label_for_class_id(class_id)
            normalized_label = _normalize_label(label)
            if target_labels and normalized_label not in target_labels:
                continue

            ymin, xmin, ymax, xmax = [float(value) for value in boxes[index]]
            x1 = int(max(0, min(frame_width - 1, xmin * frame_width)))
            y1 = int(max(0, min(frame_height - 1, ymin * frame_height)))
            x2 = int(max(0, min(frame_width - 1, xmax * frame_width)))
            y2 = int(max(0, min(frame_height - 1, ymax * frame_height)))

            if score > best_score:
                best_score = score
                best_result = FoodDetectionResult(
                    detected=True,
                    label=normalized_label,
                    raw_label=label,
                    score=score,
                    bounding_box=(x1, y1, x2, y2),
                    target_labels=self.config.target_labels,
                )

        return best_result

    def _label_for_class_id(self, class_id: int) -> str:
        if not self.labels:
            return f"class:{class_id}"

        first = _normalize_label(self.labels[0])
        index = class_id + 1 if first in {"???", "background", "__background__"} else class_id
        if 0 <= index < len(self.labels):
            return self.labels[index]
        if 0 <= class_id < len(self.labels):
            return self.labels[class_id]
        return f"class:{class_id}"

    def _parse_ssd_outputs(self, outputs: Sequence[Any]):
        boxes = classes = scores = count = None

        output_arrays = [output.squeeze() for output in outputs]
        output_names = [
            str(detail.get("name", "")).lower()
            for detail in (self._output_details or [])
        ]

        for name, array in zip(output_names, output_arrays):
            if "box" in name or "location" in name:
                boxes = array
            elif "class" in name:
                classes = array
            elif "score" in name:
                scores = array
            elif "num" in name or "count" in name:
                count = int(array.reshape(-1)[0])

        for output in output_arrays:
            array = output.squeeze()
            if boxes is None and array.ndim == 2 and array.shape[-1] == 4:
                boxes = array
            elif count is None and array.ndim == 1 and array.size == 1:
                count = int(array[0])

        remaining_vectors = [
            array
            for array in output_arrays
            if array.ndim == 1 and array.size > 1 and array is not classes and array is not scores
        ]

        if classes is None or scores is None:
            # Common SSD MobileNet TFLite output order is:
            # boxes, classes, scores, num_detections. This fallback is more
            # reliable than using values, because empty class arrays can be all 0.
            if len(remaining_vectors) >= 2:
                if classes is None:
                    classes = remaining_vectors[0]
                if scores is None:
                    scores = remaining_vectors[1]

        if classes is not None and scores is not None:
            if self._looks_like_scores(classes) and not self._looks_like_scores(scores):
                classes, scores = scores, classes

        if boxes is None or classes is None or scores is None:
            summary = []
            for index, array in enumerate(output_arrays):
                name = output_names[index] if index < len(output_names) else ""
                summary.append(f"{index}:{name}:shape={tuple(array.shape)}")
            raise RuntimeError(
                "Unsupported TFLite output format; expected SSD boxes/classes/scores. "
                + "; ".join(summary)
            )

        if count is None:
            count = min(len(boxes), len(classes), len(scores))
        return boxes, classes, scores, count

    @staticmethod
    def _looks_like_scores(values: Iterable[float]) -> bool:
        values = list(values)
        if not values:
            return False
        sample = values[: min(10, len(values))]
        return all(0.0 <= float(value) <= 1.0 for value in sample)


def draw_food_debug(frame, result: FoodDetectionResult):
    cv2 = _require_cv2()
    if result.bounding_box:
        x1, y1, x2, y2 = result.bounding_box
        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 180, 255), 2)
        label = f"food:{result.label} {result.score:.2f}"
        cv2.putText(frame, label, (x1, max(22, y1 - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 180, 255), 2)
    else:
        label = "food:none"
        cv2.putText(frame, label, (12, 112), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 180, 255), 2)
    return frame

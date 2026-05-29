"""Stop sign detection using red color or ArUco markers."""

from dataclasses import dataclass
from typing import Any, Optional, Tuple

from .config import SignDetectionConfig


@dataclass(frozen=True)
class SignResult:
    detected: bool
    method: str = "none"
    area: float = 0.0
    area_ratio: float = 0.0
    marker_ids: Tuple[int, ...] = ()
    bounding_box: Optional[Tuple[int, int, int, int]] = None
    confidence: float = 0.0
    debug_mask: Any = None


def _require_cv2():
    try:
        import cv2
    except ImportError as exc:
        raise RuntimeError("OpenCV is required for sign detection.") from exc
    return cv2


def detect_stop_sign(frame, config: Optional[SignDetectionConfig] = None, *, debug: bool = False) -> SignResult:
    config = config or SignDetectionConfig()
    cv2 = _require_cv2()

    if frame is None:
        raise ValueError("frame cannot be None")

    mode = config.mode.lower()
    if mode == "none":
        return SignResult(detected=False)

    if mode in {"both", "aruco"}:
        aruco_result = _detect_aruco(cv2, frame, config)
        if aruco_result.detected or mode == "aruco":
            return aruco_result

    if mode in {"both", "red"}:
        return _detect_red(cv2, frame, config, debug=debug)

    raise ValueError(f"Unsupported sign detection mode: {config.mode}")


def _detect_aruco(cv2, frame, config: SignDetectionConfig) -> SignResult:
    if not hasattr(cv2, "aruco"):
        return SignResult(detected=False, method="aruco")

    aruco = cv2.aruco
    dictionary_id = getattr(aruco, config.aruco_dictionary, None)
    if dictionary_id is None:
        return SignResult(detected=False, method="aruco")

    if hasattr(aruco, "getPredefinedDictionary"):
        dictionary = aruco.getPredefinedDictionary(dictionary_id)
    else:
        dictionary = aruco.Dictionary_get(dictionary_id)

    if hasattr(aruco, "DetectorParameters"):
        parameters = aruco.DetectorParameters()
    else:
        parameters = aruco.DetectorParameters_create()

    if hasattr(aruco, "ArucoDetector"):
        detector = aruco.ArucoDetector(dictionary, parameters)
        corners, ids, _ = detector.detectMarkers(frame)
    else:
        corners, ids, _ = aruco.detectMarkers(frame, dictionary, parameters=parameters)

    if ids is None or len(ids) == 0:
        return SignResult(detected=False, method="aruco")

    found_ids = tuple(int(marker_id) for marker_id in ids.flatten())
    targets = set(config.target_aruco_ids)
    if targets and not any(marker_id in targets for marker_id in found_ids):
        return SignResult(detected=False, method="aruco", marker_ids=found_ids)

    points = corners[0].reshape(-1, 2)
    x_min = int(points[:, 0].min())
    y_min = int(points[:, 1].min())
    x_max = int(points[:, 0].max())
    y_max = int(points[:, 1].max())
    area = float(max(0, x_max - x_min) * max(0, y_max - y_min))
    frame_area = float(frame.shape[0] * frame.shape[1])

    return SignResult(
        detected=True,
        method="aruco",
        area=area,
        area_ratio=area / frame_area if frame_area else 0.0,
        marker_ids=found_ids,
        bounding_box=(x_min, y_min, x_max, y_max),
        confidence=1.0,
    )


def _detect_red(cv2, frame, config: SignDetectionConfig, *, debug: bool = False) -> SignResult:
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    lower_red_1 = (0, config.red_min_saturation, config.red_min_value)
    upper_red_1 = (10, 255, 255)
    lower_red_2 = (170, config.red_min_saturation, config.red_min_value)
    upper_red_2 = (180, 255, 255)

    mask_1 = cv2.inRange(hsv, lower_red_1, upper_red_1)
    mask_2 = cv2.inRange(hsv, lower_red_2, upper_red_2)
    mask = cv2.bitwise_or(mask_1, mask_2)

    kernel_size = max(1, int(config.morph_kernel_size))
    if kernel_size > 1:
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (kernel_size, kernel_size))
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

    contours_info = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    contours = contours_info[-2]
    if not contours:
        return SignResult(detected=False, method="red", debug_mask=mask if debug else None)

    contour = max(contours, key=cv2.contourArea)
    area = float(cv2.contourArea(contour))
    frame_area = float(frame.shape[0] * frame.shape[1])
    area_ratio = area / frame_area if frame_area else 0.0
    x, y, w, h = cv2.boundingRect(contour)
    detected = area >= config.red_area_min or area_ratio >= config.red_area_ratio_min

    return SignResult(
        detected=detected,
        method="red",
        area=area,
        area_ratio=area_ratio,
        bounding_box=(x, y, x + w, y + h),
        confidence=min(1.0, area_ratio / max(config.red_area_ratio_min, 0.0001)),
        debug_mask=mask if debug else None,
    )


def draw_sign_debug(frame, result: SignResult):
    cv2 = _require_cv2()
    if result.bounding_box:
        x1, y1, x2, y2 = result.bounding_box
        color = (0, 0, 255) if result.detected else (120, 120, 120)
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
    label = f"sign={result.method}:{result.detected}"
    cv2.putText(frame, label, (12, 52), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2, cv2.LINE_AA)
    return frame

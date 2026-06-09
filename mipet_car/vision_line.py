"""Line detection for tape-based path following."""

from dataclasses import dataclass
from typing import Any, Optional, Tuple

from .config import LineDetectionConfig


@dataclass(frozen=True)
class LineResult:
    found: bool
    offset: Optional[float]
    center_x: Optional[float]
    frame_center_x: float
    frame_width: int
    frame_height: int
    area: float = 0.0
    confidence: float = 0.0
    roi: Tuple[int, int, int, int] = (0, 0, 0, 0)
    mask: Any = None
    debug_frame: Any = None


def _require_cv2():
    try:
        import cv2
    except ImportError as exc:
        raise RuntimeError("OpenCV is required for line detection.") from exc
    return cv2


def _build_mask(cv2, roi, config: LineDetectionConfig):
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    if config.mode == "black":
        return cv2.inRange(hsv, (0, 0, 0), (180, 255, config.black_value_max))
    if config.mode == "color":
        return cv2.inRange(hsv, config.color_lower_hsv, config.color_upper_hsv)
    raise ValueError(f"Unsupported line detection mode: {config.mode}")


def detect_line(frame, config: Optional[LineDetectionConfig] = None, *, debug: bool = False) -> LineResult:
    config = config or LineDetectionConfig()
    cv2 = _require_cv2()

    if frame is None:
        raise ValueError("frame cannot be None")

    frame_height, frame_width = frame.shape[:2]
    frame_center_x = frame_width / 2.0
    y1 = int(frame_height * config.roi_top_ratio)
    y2 = int(frame_height * config.roi_bottom_ratio)
    y1 = max(0, min(frame_height - 1, y1))
    y2 = max(y1 + 1, min(frame_height, y2))
    roi = frame[y1:y2, :]

    mask = _build_mask(cv2, roi, config)
    kernel_size = max(1, int(config.morph_kernel_size))
    if kernel_size > 1:
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (kernel_size, kernel_size))
        if config.mode == "black":
            # Opening erodes thin tape lines and can make a valid line disappear.
            # Closing keeps the line while filling tiny camera/noise gaps.
            mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        else:
            mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
            mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

    contours_info = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    contours = contours_info[-2]
    debug_frame = frame.copy() if debug else None
    roi_bounds = (0, y1, frame_width, y2)

    if debug_frame is not None:
        cv2.rectangle(debug_frame, (0, y1), (frame_width - 1, y2 - 1), (255, 200, 0), 1)
        cv2.line(
            debug_frame,
            (int(frame_center_x), y1),
            (int(frame_center_x), y2),
            (255, 0, 0),
            1,
        )

    if not contours:
        return LineResult(
            found=False,
            offset=None,
            center_x=None,
            frame_center_x=frame_center_x,
            frame_width=frame_width,
            frame_height=frame_height,
            roi=roi_bounds,
            mask=mask if debug else None,
            debug_frame=debug_frame,
        )

    contour = max(contours, key=cv2.contourArea)
    area = float(cv2.contourArea(contour))
    roi_area = float(roi.shape[0] * roi.shape[1])
    confidence = area / roi_area if roi_area else 0.0
    moments = cv2.moments(contour)

    if area < config.min_area or moments["m00"] == 0:
        return LineResult(
            found=False,
            offset=None,
            center_x=None,
            frame_center_x=frame_center_x,
            frame_width=frame_width,
            frame_height=frame_height,
            area=area,
            confidence=confidence,
            roi=roi_bounds,
            mask=mask if debug else None,
            debug_frame=debug_frame,
        )

    center_x = float(moments["m10"] / moments["m00"])
    offset = center_x - frame_center_x

    if debug_frame is not None:
        debug_roi = debug_frame[y1:y2, :]
        cv2.drawContours(debug_roi, [contour], -1, (0, 255, 0), 2)
        cv2.line(
            debug_frame,
            (int(center_x), y1),
            (int(center_x), y2),
            (0, 255, 255),
            2,
        )
        cv2.putText(
            debug_frame,
            f"line offset={offset:.1f}",
            (12, max(24, y1 - 10)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (0, 255, 255),
            2,
            cv2.LINE_AA,
        )

    return LineResult(
        found=True,
        offset=offset,
        center_x=center_x,
        frame_center_x=frame_center_x,
        frame_width=frame_width,
        frame_height=frame_height,
        area=area,
        confidence=confidence,
        roi=roi_bounds,
        mask=mask if debug else None,
        debug_frame=debug_frame,
    )

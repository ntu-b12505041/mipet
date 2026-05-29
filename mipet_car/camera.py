"""Camera capture helpers for OpenCV and Picamera2."""

from typing import Iterator, Optional, Union

from .config import CameraConfig


class CameraError(RuntimeError):
    """Raised when a camera cannot be opened or read."""


def parse_camera_source(source: Union[str, int]) -> Union[str, int]:
    if isinstance(source, int):
        return source
    source = str(source)
    if source.isdigit():
        return int(source)
    return source


def _require_cv2():
    try:
        import cv2
    except ImportError as exc:
        raise CameraError("OpenCV is required for camera capture.") from exc
    return cv2


class Camera:
    def __init__(self, config: Optional[CameraConfig] = None) -> None:
        self.config = config or CameraConfig()
        self._capture = None
        self._picamera2 = None
        self._cv2 = None

    def open(self) -> None:
        if self._capture is not None or self._picamera2 is not None:
            return

        if self.config.backend == "opencv":
            self._open_opencv()
            return
        if self.config.backend == "picamera2":
            self._open_picamera2()
            return
        raise CameraError(f"Unsupported camera backend: {self.config.backend}")

    def _open_opencv(self) -> None:
        cv2 = _require_cv2()
        self._cv2 = cv2
        source = parse_camera_source(self.config.source)
        capture = cv2.VideoCapture(source)
        if self.config.width:
            capture.set(cv2.CAP_PROP_FRAME_WIDTH, self.config.width)
        if self.config.height:
            capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self.config.height)
        if self.config.fps:
            capture.set(cv2.CAP_PROP_FPS, self.config.fps)

        if not capture.isOpened():
            raise CameraError(f"Cannot open camera source: {self.config.source}")
        self._capture = capture

    def _open_picamera2(self) -> None:
        cv2 = _require_cv2()
        self._cv2 = cv2
        try:
            from picamera2 import Picamera2
        except ImportError as exc:
            raise CameraError("Picamera2 is required for backend='picamera2'.") from exc

        camera = Picamera2()
        video_config = camera.create_video_configuration(
            main={
                "size": (self.config.width, self.config.height),
                "format": "RGB888",
            }
        )
        camera.configure(video_config)
        camera.start()
        self._picamera2 = camera

    def read(self):
        if self._capture is None and self._picamera2 is None:
            self.open()

        if self._picamera2 is not None:
            frame_rgb = self._picamera2.capture_array()
            return self._cv2.cvtColor(frame_rgb, self._cv2.COLOR_RGB2BGR)

        ok, frame = self._capture.read()
        if not ok or frame is None:
            raise CameraError("Camera returned no frame.")
        return frame

    def frames(self) -> Iterator:
        while True:
            yield self.read()

    def release(self) -> None:
        if self._capture is not None:
            self._capture.release()
            self._capture = None
        if self._picamera2 is not None:
            self._picamera2.stop()
            self._picamera2.close()
            self._picamera2 = None

    def __enter__(self) -> "Camera":
        self.open()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.release()

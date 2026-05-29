"""Flask MJPEG stream for camera and vision testing over SSH."""

import argparse
from dataclasses import replace
import logging
import threading
import time
from typing import Dict, Optional

from flask import Flask, Response, jsonify

from .camera import Camera, CameraError
from .config import CameraConfig, DriveConfig, FoodDetectionConfig, LineDetectionConfig, SignDetectionConfig
from .decision import DriveState, MotorCommand, decide
from .vision_food import FoodDetector, draw_food_debug
from .vision_line import detect_line
from .vision_sign import detect_stop_sign, draw_sign_debug


LOGGER = logging.getLogger("mipet_car.web_stream")


PAGE = """<!doctype html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>MiPet Camera Stream</title>
  <style>
    body {
      margin: 0;
      background: #101418;
      color: #f3f6f8;
      font-family: Arial, "Microsoft JhengHei", sans-serif;
    }
    main {
      max-width: 980px;
      margin: 0 auto;
      padding: 18px;
    }
    h1 {
      font-size: 22px;
      margin: 0 0 14px;
      font-weight: 700;
    }
    img {
      width: 100%;
      background: #050607;
      border: 1px solid #2a333b;
      display: block;
    }
    .status {
      margin-top: 12px;
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
      gap: 8px;
    }
    .item {
      border: 1px solid #2a333b;
      padding: 10px 12px;
      background: #171d22;
    }
    .label {
      color: #aab5bd;
      font-size: 12px;
      margin-bottom: 4px;
    }
    .value {
      font-size: 18px;
      font-weight: 700;
    }
  </style>
</head>
<body>
  <main>
    <h1>MiPet Camera Stream</h1>
    <img src="/stream.mjpg" alt="MiPet camera stream">
    <section class="status">
      <div class="item"><div class="label">State</div><div class="value" id="state">--</div></div>
      <div class="item"><div class="label">Offset</div><div class="value" id="offset">--</div></div>
      <div class="item"><div class="label">Motor</div><div class="value" id="motor">--</div></div>
      <div class="item"><div class="label">Food</div><div class="value" id="food">--</div></div>
      <div class="item"><div class="label">Sign</div><div class="value" id="sign">--</div></div>
    </section>
  </main>
  <script>
    async function refreshStatus() {
      try {
        const response = await fetch('/status.json', {cache: 'no-store'});
        const data = await response.json();
        document.getElementById('state').textContent = data.state || '--';
        document.getElementById('offset').textContent =
          data.offset === null || data.offset === undefined ? '--' : Number(data.offset).toFixed(1);
        document.getElementById('motor').textContent =
          `${Number(data.left_speed || 0).toFixed(2)} / ${Number(data.right_speed || 0).toFixed(2)}`;
        document.getElementById('food').textContent = data.food_detected
          ? `${data.food_label} ${Number(data.food_score || 0).toFixed(2)}`
          : 'no';
        document.getElementById('sign').textContent = data.sign_detected ? data.sign_method : 'no';
      } catch (error) {
        document.getElementById('state').textContent = 'offline';
      }
    }
    setInterval(refreshStatus, 500);
    refreshStatus();
  </script>
</body>
</html>
"""


def _require_cv2():
    try:
        import cv2
    except ImportError as exc:
        raise RuntimeError("OpenCV is required for MJPEG streaming.") from exc
    return cv2


def _draw_command(frame, command: MotorCommand):
    cv2 = _require_cv2()
    text = f"{command.state.value} L={command.left_speed:.2f} R={command.right_speed:.2f}"
    cv2.putText(frame, text, (12, 82), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 3, cv2.LINE_AA)
    cv2.putText(frame, text, (12, 82), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (20, 20, 20), 1, cv2.LINE_AA)
    return frame


class StreamWorker:
    def __init__(
        self,
        camera_config: CameraConfig,
        line_config: LineDetectionConfig,
        sign_config: SignDetectionConfig,
        food_config: FoodDetectionConfig,
        drive_config: DriveConfig,
        *,
        jpeg_quality: int = 80,
        food_stop_seconds: float = 5.0,
    ) -> None:
        self.camera_config = camera_config
        self.line_config = line_config
        self.sign_config = sign_config
        self.food_config = food_config
        self.drive_config = drive_config
        self.jpeg_quality = jpeg_quality
        self.food_stop_seconds = food_stop_seconds
        self._food_stop_until = 0.0
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._latest_jpeg: Optional[bytes] = None
        self._status: Dict[str, object] = {
            "state": "START",
            "offset": None,
            "left_speed": 0.0,
            "right_speed": 0.0,
            "sign_detected": False,
            "sign_method": "none",
            "food_detected": False,
            "food_label": "",
            "food_score": 0.0,
            "error": None,
        }

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run, name="mipet-stream", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2.0)

    def status(self) -> Dict[str, object]:
        with self._lock:
            return dict(self._status)

    def latest_jpeg(self) -> Optional[bytes]:
        with self._lock:
            return self._latest_jpeg

    def _set_error(self, message: str) -> None:
        with self._lock:
            self._status["error"] = message
            self._status["state"] = "ERROR"

    def _run(self) -> None:
        cv2 = _require_cv2()
        encode_params = [int(cv2.IMWRITE_JPEG_QUALITY), int(self.jpeg_quality)]
        last_log_at = 0.0

        try:
            food_detector = FoodDetector(self.food_config)
            if food_detector.enabled:
                LOGGER.info("Food detector enabled for: %s", ", ".join(self.food_config.target_labels))

            with Camera(self.camera_config) as camera:
                while not self._stop.is_set():
                    frame = camera.read()
                    sign_result = detect_stop_sign(frame, self.sign_config, debug=False)
                    food_result = food_detector.detect(frame)
                    line_result = detect_line(frame, self.line_config, debug=True)
                    now = time.monotonic()
                    if self._food_stop_until > now:
                        remaining = self._food_stop_until - now
                        command = MotorCommand.stop(DriveState.FOOD_DETECTED, f"food pause {remaining:.1f}s")
                    else:
                        command = decide(line_result, sign_result, food_result, self.drive_config)
                        if command.state == DriveState.FOOD_DETECTED:
                            self._food_stop_until = now + self.food_stop_seconds

                    debug_frame = line_result.debug_frame if line_result.debug_frame is not None else frame.copy()
                    draw_sign_debug(debug_frame, sign_result)
                    draw_food_debug(debug_frame, food_result)
                    _draw_command(debug_frame, command)

                    ok, encoded = cv2.imencode(".jpg", debug_frame, encode_params)
                    if not ok:
                        continue

                    with self._lock:
                        self._latest_jpeg = encoded.tobytes()
                        self._status = {
                            "state": command.state.value,
                            "offset": line_result.offset,
                            "line_found": line_result.found,
                            "left_speed": command.left_speed,
                            "right_speed": command.right_speed,
                            "sign_detected": sign_result.detected,
                            "sign_method": sign_result.method,
                            "food_detected": food_result.detected,
                            "food_label": food_result.label,
                            "food_score": food_result.score,
                            "reason": command.reason,
                            "error": None,
                        }

                    if now - last_log_at > 2.0:
                        LOGGER.info("%s %s", command.state.value, command.reason)
                        last_log_at = now

        except CameraError as exc:
            self._set_error(str(exc))
            LOGGER.error("%s", exc)
        except Exception as exc:
            self._set_error(str(exc))
            LOGGER.exception("Stream worker stopped unexpectedly.")


def create_app(worker: StreamWorker) -> Flask:
    app = Flask(__name__)

    @app.get("/")
    def index():
        return PAGE

    @app.get("/status.json")
    def status():
        return jsonify(worker.status())

    @app.get("/stream.mjpg")
    def stream():
        def generate():
            while True:
                frame = worker.latest_jpeg()
                if frame is None:
                    time.sleep(0.05)
                    continue
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n"
                    b"Cache-Control: no-store\r\n\r\n" + frame + b"\r\n"
                )
                time.sleep(0.03)

        return Response(generate(), mimetype="multipart/x-mixed-replace; boundary=frame")

    return app


def build_parser() -> argparse.ArgumentParser:
    default_drive = DriveConfig()
    parser = argparse.ArgumentParser(description="MiPet Flask camera stream")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--camera", default="0")
    parser.add_argument("--backend", choices=["opencv", "picamera2"], default="opencv")
    parser.add_argument("--line-mode", choices=["black", "color"], default="black")
    parser.add_argument("--sign-mode", choices=["both", "red", "aruco", "none"], default="both")
    parser.add_argument("--food-model", default="", help="Path to a TFLite SSD MobileNet model.")
    parser.add_argument("--food-labels", default="", help="Path to labels file for the TFLite model.")
    parser.add_argument("--food-threshold", type=float, default=0.50)
    parser.add_argument("--food-classes", default="banana,apple,orange,bottle,cup,bowl")
    parser.add_argument("--food-stop-seconds", type=float, default=5.0)
    parser.add_argument("--base-speed", type=float, default=default_drive.base_speed)
    parser.add_argument("--max-speed", type=float, default=default_drive.max_speed)
    parser.add_argument("--kp", type=float, default=default_drive.kp)
    parser.add_argument("--deadband-px", type=float, default=default_drive.deadband_px)
    parser.add_argument("--jpeg-quality", type=int, default=80)
    return parser


def run(args: argparse.Namespace) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    camera_config = replace(CameraConfig(), source=args.camera, backend=args.backend)
    line_config = replace(LineDetectionConfig(), mode=args.line_mode)
    sign_config = replace(SignDetectionConfig(), mode=args.sign_mode)
    food_config = FoodDetectionConfig(
        model_path=args.food_model,
        labels_path=args.food_labels,
        score_threshold=args.food_threshold,
        target_labels=tuple(label.strip() for label in args.food_classes.split(",") if label.strip()),
    )
    drive_config = replace(
        DriveConfig(),
        base_speed=args.base_speed,
        max_speed=args.max_speed,
        kp=args.kp,
        deadband_px=args.deadband_px,
    )

    worker = StreamWorker(
        camera_config,
        line_config,
        sign_config,
        food_config,
        drive_config,
        jpeg_quality=args.jpeg_quality,
        food_stop_seconds=args.food_stop_seconds,
    )
    worker.start()
    app = create_app(worker)
    try:
        app.run(host=args.host, port=args.port, threaded=True, use_reloader=False)
    finally:
        worker.stop()
    return 0


def main() -> int:
    return run(build_parser().parse_args())


if __name__ == "__main__":
    raise SystemExit(main())

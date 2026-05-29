"""Main runtime loop for the MiPet car."""

import argparse
from dataclasses import replace
import logging
import time

from .camera import Camera, CameraError
from .config import CameraConfig, DriveConfig, FoodDetectionConfig, LineDetectionConfig, MotorConfig, SignDetectionConfig
from .decision import DriveState, MotorCommand, decide
from .motor import MotorDriver
from .vision_food import FoodDetector, draw_food_debug
from .vision_line import detect_line
from .vision_sign import detect_stop_sign, draw_sign_debug


LOGGER = logging.getLogger("mipet_car")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="MiPet Raspberry Pi self-driving car")
    default_drive = DriveConfig()
    parser.add_argument("--camera", default="0", help="Camera index or video path. Default: 0")
    parser.add_argument("--backend", choices=["opencv", "picamera2"], default="opencv")
    parser.add_argument("--dry-run", action="store_true", help="Do not touch GPIO; print decisions only.")
    parser.add_argument("--debug", action="store_true", help="Show OpenCV debug window and overlays.")
    parser.add_argument("--headless", action="store_true", help="Do not open a GUI window.")
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
    parser.add_argument("--max-frames", type=int, default=0, help="Stop after this many frames. 0 means forever.")
    parser.add_argument(
        "--no-stop-latch",
        action="store_true",
        help="Allow the car to resume if the stop sign disappears.",
    )
    return parser


def _require_cv2_for_debug():
    try:
        import cv2
    except ImportError as exc:
        raise RuntimeError("OpenCV is required for --debug display.") from exc
    return cv2


def _draw_command(frame, command: MotorCommand):
    cv2 = _require_cv2_for_debug()
    text = f"{command.state.value} L={command.left_speed:.2f} R={command.right_speed:.2f}"
    cv2.putText(frame, text, (12, 82), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 3, cv2.LINE_AA)
    cv2.putText(frame, text, (12, 82), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (20, 20, 20), 1, cv2.LINE_AA)
    return frame


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

    stop_latched = False
    food_stop_until = 0.0
    frame_count = 0
    last_log_at = 0.0
    cv2 = _require_cv2_for_debug() if args.debug and not args.headless else None

    try:
        food_detector = FoodDetector(food_config)
        if food_detector.enabled:
            LOGGER.info("Food detector enabled for: %s", ", ".join(food_config.target_labels))

        with Camera(camera_config) as camera, MotorDriver(MotorConfig(), dry_run=args.dry_run) as motor:
            if motor.using_mock:
                LOGGER.info("Motor is in dry-run/mock mode.")

            while True:
                frame = camera.read()
                frame_count += 1

                sign_result = detect_stop_sign(frame, sign_config, debug=args.debug)
                food_result = food_detector.detect(frame)
                line_result = detect_line(frame, line_config, debug=args.debug and not args.headless)

                now = time.monotonic()
                if food_stop_until > now:
                    remaining = food_stop_until - now
                    command = MotorCommand.stop(DriveState.FOOD_DETECTED, f"food pause {remaining:.1f}s")
                elif stop_latched:
                    command = MotorCommand.stop(DriveState.STOP_SIGN_DETECTED, "stop latch active")
                else:
                    command = decide(line_result, sign_result, food_result, drive_config)
                    if command.state == DriveState.FOOD_DETECTED:
                        food_stop_until = now + args.food_stop_seconds
                    elif command.state == DriveState.STOP_SIGN_DETECTED and not args.no_stop_latch:
                        stop_latched = True

                motor.set_speed(command.left_speed, command.right_speed)

                if now - last_log_at >= 0.5:
                    LOGGER.info(
                        "%s left=%.2f right=%.2f %s",
                        command.state.value,
                        command.left_speed,
                        command.right_speed,
                        command.reason,
                    )
                    last_log_at = now

                if cv2 is not None:
                    debug_frame = line_result.debug_frame if line_result.debug_frame is not None else frame.copy()
                    draw_sign_debug(debug_frame, sign_result)
                    draw_food_debug(debug_frame, food_result)
                    _draw_command(debug_frame, command)
                    cv2.imshow("MiPet debug", debug_frame)
                    if cv2.waitKey(1) & 0xFF == ord("q"):
                        break

                if args.max_frames and frame_count >= args.max_frames:
                    break

    except KeyboardInterrupt:
        LOGGER.info("Interrupted by user.")
    except CameraError as exc:
        LOGGER.error("%s", exc)
        return 2
    finally:
        if cv2 is not None:
            cv2.destroyAllWindows()

    return 0


def main() -> int:
    return run(build_parser().parse_args())


if __name__ == "__main__":
    raise SystemExit(main())

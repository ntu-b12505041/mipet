"""Manual motor smoke test."""

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mipet_car.motor import MotorDriver, MotorHardwareError


def main() -> int:
    parser = argparse.ArgumentParser(description="TB6612 manual motor test")
    parser.add_argument("--dry-run", action="store_true", help="Do not use GPIO.")
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip the safety confirmation prompt for live GPIO tests.",
    )
    parser.add_argument("--speed", type=float, default=0.35)
    parser.add_argument("--seconds", type=float, default=1.0)
    parser.add_argument(
        "--mode",
        choices=[
            "sequence",
            "left-forward",
            "left-backward",
            "right-forward",
            "right-backward",
            "both-forward",
            "both-backward",
            "turn-left",
            "turn-right",
            "stop",
        ],
        default="sequence",
        help="Motor test mode. Use left/right modes first for safer wiring checks.",
    )
    args = parser.parse_args()

    modes = {
        "left-forward": [("left_forward", lambda motor: motor.set_speed(args.speed, 0.0))],
        "left-backward": [("left_backward", lambda motor: motor.set_speed(-args.speed, 0.0))],
        "right-forward": [("right_forward", lambda motor: motor.set_speed(0.0, args.speed))],
        "right-backward": [("right_backward", lambda motor: motor.set_speed(0.0, -args.speed))],
        "both-forward": [("both_forward", lambda motor: motor.forward(args.speed))],
        "both-backward": [("both_backward", lambda motor: motor.backward(args.speed))],
        "turn-left": [("turn_left", lambda motor: motor.turn_left(args.speed))],
        "turn-right": [("turn_right", lambda motor: motor.turn_right(args.speed))],
        "stop": [("stop", lambda motor: motor.stop())],
    }
    modes["sequence"] = [
        ("left_forward", lambda motor: motor.set_speed(args.speed, 0.0)),
        ("right_forward", lambda motor: motor.set_speed(0.0, args.speed)),
        ("both_forward", lambda motor: motor.forward(args.speed)),
        ("both_backward", lambda motor: motor.backward(args.speed)),
        ("turn_left", lambda motor: motor.turn_left(args.speed)),
        ("turn_right", lambda motor: motor.turn_right(args.speed)),
        ("stop", lambda motor: motor.stop()),
    ]

    if not args.dry_run and not args.yes:
        print("Safety: lift the car so both wheels are off the table before continuing.")
        try:
            input("Press Enter to start the live motor test, or Ctrl+C to cancel.")
        except EOFError:
            print("No keyboard input is available. Re-run with --yes after lifting the car.")
            return 2

    try:
        with MotorDriver(
            dry_run=args.dry_run,
            allow_mock_fallback=args.dry_run,
        ) as motor:
            print(f"motor mock mode: {motor.using_mock}")
            for name, action in modes[args.mode]:
                print(name)
                action(motor)
                print(motor.snapshot())
                time.sleep(args.seconds)
            motor.stop()
    except MotorHardwareError as exc:
        print(f"Motor hardware error: {exc}")
        print("On Raspberry Pi, install GPIO support: sudo apt install -y python3-gpiozero")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

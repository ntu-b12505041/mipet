"""Manual camera preview test."""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mipet_car.camera import Camera
from mipet_car.config import CameraConfig


def main() -> int:
    parser = argparse.ArgumentParser(description="Camera preview test")
    parser.add_argument("--camera", default="0")
    args = parser.parse_args()

    import cv2

    with Camera(CameraConfig(source=args.camera)) as camera:
        while True:
            frame = camera.read()
            cv2.imshow("MiPet camera test", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

    cv2.destroyAllWindows()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


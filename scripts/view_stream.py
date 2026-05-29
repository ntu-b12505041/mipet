"""Show the Raspberry Pi MJPEG stream in a local OpenCV window."""

import argparse
import time
import urllib.request


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="View MiPet Raspberry Pi stream with cv2.imshow")
    parser.add_argument(
        "--url",
        default="http://172.20.10.2:5000/stream.mjpg",
        help="MJPEG stream URL from the Raspberry Pi.",
    )
    parser.add_argument("--window", default="MiPet Raspberry Pi Stream")
    parser.add_argument("--timeout", type=float, default=10.0)
    return parser


def iter_jpeg_frames(url: str, timeout: float):
    import cv2
    import numpy as np

    with urllib.request.urlopen(url, timeout=timeout) as response:
        buffer = b""
        while True:
            chunk = response.read(4096)
            if not chunk:
                time.sleep(0.02)
                continue
            buffer += chunk

            start = buffer.find(b"\xff\xd8")
            end = buffer.find(b"\xff\xd9")
            if start == -1 or end == -1 or end < start:
                if len(buffer) > 2_000_000:
                    buffer = buffer[-200_000:]
                continue

            jpg = buffer[start : end + 2]
            buffer = buffer[end + 2 :]
            frame = cv2.imdecode(np.frombuffer(jpg, dtype=np.uint8), cv2.IMREAD_COLOR)
            if frame is not None:
                yield frame


def main() -> int:
    args = build_parser().parse_args()

    import cv2

    print(f"Opening {args.url}")
    print("Press q to close the window.")

    try:
        for frame in iter_jpeg_frames(args.url, args.timeout):
            cv2.imshow(args.window, frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    except KeyboardInterrupt:
        pass
    finally:
        cv2.destroyAllWindows()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

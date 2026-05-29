"""Download the starter TensorFlow Lite object detection model."""

import argparse
from pathlib import Path
import shutil
import tempfile
import urllib.request
import zipfile


MODEL_URL = (
    "https://storage.googleapis.com/download.tensorflow.org/models/tflite/"
    "coco_ssd_mobilenet_v1_1.0_quant_2018_06_29.zip"
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Download COCO SSD MobileNet TFLite model")
    parser.add_argument("--output-dir", default="models", help="Directory to write detect.tflite and labelmap.txt.")
    parser.add_argument("--url", default=MODEL_URL, help="Model zip URL.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as temp_dir_name:
        temp_dir = Path(temp_dir_name)
        zip_path = temp_dir / "model.zip"

        print(f"Downloading {args.url}")
        urllib.request.urlretrieve(args.url, zip_path)

        with zipfile.ZipFile(zip_path) as archive:
            archive.extractall(temp_dir)

        detect_candidates = list(temp_dir.rglob("detect.tflite"))
        label_candidates = list(temp_dir.rglob("labelmap.txt"))
        if not detect_candidates or not label_candidates:
            raise RuntimeError("Downloaded zip did not contain detect.tflite and labelmap.txt.")

        shutil.copy2(detect_candidates[0], output_dir / "detect.tflite")
        shutil.copy2(label_candidates[0], output_dir / "labelmap.txt")

    print(f"Wrote {output_dir / 'detect.tflite'}")
    print(f"Wrote {output_dir / 'labelmap.txt'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

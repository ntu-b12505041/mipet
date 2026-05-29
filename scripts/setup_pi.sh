#!/usr/bin/env bash
set -euo pipefail

sudo apt update
sudo apt install -y python3-venv python3-opencv python3-gpiozero python3-numpy python3-flask python3-picamera2 python3-pip

if [ ! -d .venv ]; then
  python3 -m venv --system-site-packages .venv
fi

. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install tflite-runtime || python -m pip install ai-edge-litert
python -m unittest discover -s tests

echo "MiPet Raspberry Pi setup complete."
echo "Next: source .venv/bin/activate"
echo "Then: python scripts/stream_camera.py --host 0.0.0.0 --port 5000 --camera 0"

# Food Detection Models

Put TensorFlow Lite object detection files here on the Raspberry Pi.

Recommended first model type:

- SSD MobileNet TFLite model, for example `detect.tflite`
- COCO labels file, for example `labelmap.txt`

Download the starter model:

```bash
python scripts/download_food_model.py
```

Run with:

```bash
python scripts/stream_camera.py \
  --host 0.0.0.0 \
  --port 5000 \
  --backend picamera2 \
  --sign-mode none \
  --food-model models/detect.tflite \
  --food-labels models/labelmap.txt \
  --food-classes banana,apple,orange,bottle,cup,bowl \
  --food-threshold 0.50 \
  --food-stop-seconds 5
```

The code expects SSD-style outputs: boxes, classes, scores, and optional count.

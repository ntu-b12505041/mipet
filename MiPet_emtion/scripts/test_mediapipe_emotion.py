"""
scripts/test_mediapipe_emotion.py
用 MediaPipe 對靜態照片做表情辨識測試

用法：
  python3 scripts/test_mediapipe_emotion.py                        # 跑所有 testPic
  python3 scripts/test_mediapipe_emotion.py dataset/testPic_013.jpg  # 單張
"""

import sys
import os
import pathlib
import cv2
import numpy as np
import mediapipe as mp
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision as mp_vision

MODEL_PATH = "model/face_landmarker.task"
MODEL_URL  = "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task"

EMOJI = {
    "happy":   "😊",
    "sad":     "😢",
    "angry":   "😠",
    "fearful": "😨",
    "neutral": "😐",
}

def _download_model():
    if not os.path.exists(MODEL_PATH):
        os.makedirs("model", exist_ok=True)
        print(f"下載 MediaPipe 模型...")
        import urllib.request
        urllib.request.urlretrieve(MODEL_URL, MODEL_PATH)
        print("下載完成")

def _build_detector():
    _download_model()
    base_opts = mp_python.BaseOptions(model_asset_path=MODEL_PATH)
    opts = mp_vision.FaceLandmarkerOptions(
        base_options=base_opts,
        output_face_blendshapes=True,
        num_faces=4,
    )
    return mp_vision.FaceLandmarker.create_from_options(opts)

def _blendshapes_to_emotion(blendshapes) -> tuple[str, dict]:
    """將 blendshape 分數對應到情緒標籤"""
    scores = {b.category_name: b.score for b in blendshapes}

    happy   = scores.get("mouthSmileLeft", 0) + scores.get("mouthSmileRight", 0)
    sad     = scores.get("mouthFrownLeft", 0) + scores.get("mouthFrownRight", 0)
    angry   = scores.get("browDownLeft", 0)   + scores.get("browDownRight", 0)
    fearful = scores.get("eyeWideLeft", 0)    + scores.get("eyeWideRight", 0)

    emotions = {
        "happy":   round(happy   * 50, 1),
        "sad":     round(sad     * 50, 1),
        "angry":   round(angry   * 50, 1),
        "fearful": round(fearful * 50, 1),
    }
    emotions["neutral"] = round(max(0, 100 - sum(emotions.values())), 1)

    dominant = max(emotions, key=lambda k: emotions[k])
    return dominant, emotions

def analyze_one(img_path: str, detector):
    try:
        img = mp.Image.create_from_file(img_path)
        result = detector.detect(img)

        if not result.face_landmarks:
            print("  ❌ 找不到人臉")
            return

        for i, blendshapes in enumerate(result.face_blendshapes):
            dominant, emotions = _blendshapes_to_emotion(blendshapes)
            top3 = sorted(emotions.items(), key=lambda x: x[1], reverse=True)[:3]
            top3_str = "  ".join(f"{EMOJI.get(e,'?')}{e}:{s}%" for e, s in top3)
            label = f"人臉#{i+1} " if len(result.face_blendshapes) > 1 else ""
            print(f"  {label}{EMOJI.get(dominant,'?')} {dominant:<10} | {top3_str}")

    except Exception as ex:
        print(f"  ❌ 錯誤：{ex}")

def run_all(detector):
    pics = sorted(pathlib.Path("dataset").glob("testPic_*.jpg"),
                  key=lambda p: int(p.stem.split("_")[1]))
    print(f"{'圖片':<18} 結果")
    print("-" * 65)
    for p in pics:
        print(f"{p.name:<18}", end="", flush=True)
        analyze_one(str(p), detector)

if __name__ == "__main__":
    detector = _build_detector()
    if len(sys.argv) > 1:
        print(f"分析：{sys.argv[1]}")
        analyze_one(sys.argv[1], detector)
    else:
        run_all(detector)

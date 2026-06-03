"""
scripts/test_recognition.py
Step 3: 用一張測試照片，看模型能不能正確辨識

執行：python3 scripts/test_recognition.py <照片路徑>
例如：python3 scripts/test_recognition.py test.jpg
"""

import face_recognition
import pickle
import numpy as np
import sys
import os

MODEL_FILE = "model/face_model.pkl"

def predict(img_path: str, threshold: float = None):
    """
    輸入一張照片路徑
    回傳：(label, distance, is_owner)
    """
    # 載入模型
    with open(MODEL_FILE, "rb") as f:
        model_data = pickle.load(f)

    knn = model_data["knn"]
    if threshold is None:
        threshold = model_data.get("threshold", 0.5)

    # 讀取測試照片
    print(f"\n📷 分析照片：{img_path}")
    image = face_recognition.load_image_file(img_path)

    # 偵測人臉
    face_locations = face_recognition.face_locations(image, model="hog")
    if len(face_locations) == 0:
        print("❌ 找不到人臉！")
        return None, None, False

    print(f"✅ 偵測到 {len(face_locations)} 個人臉")

    results = []
    for i, face_loc in enumerate(face_locations):
        # 提取特徵向量
        encoding = face_recognition.face_encodings(image, [face_loc])[0]

        # KNN 預測
        distances, indices = knn.kneighbors([encoding], n_neighbors=model_data["k"])
        min_distance = distances[0][0]
        predicted_label = knn.predict([encoding])[0]

        # 距離超過閾值 → unknown（陌生人）
        if min_distance > threshold:
            final_label = "unknown"
            is_owner = False
        else:
            final_label = predicted_label
            is_owner = (final_label != "unknown")

        results.append((final_label, min_distance, is_owner))

        print(f"\n  人臉 #{i+1}：")
        print(f"  預測結果：{final_label}")
        print(f"  最近距離：{min_distance:.4f}（閾值：{threshold}）")

        if is_owner:
            print(f"  判定：✅ 是 {final_label}（認識的人）")
        else:
            print(f"  判定：🚫 陌生人（unknown）")

        # 顯示最近的 K 個鄰居
        print(f"  最近 {model_data['k']} 個鄰居距離：{[f'{d:.3f}' for d in distances[0]]}")

    return results

def main():
    if len(sys.argv) < 2:
        print("用法：python3 scripts/test_recognition.py <照片路徑>")
        print("例如：python3 scripts/test_recognition.py test.jpg")
        sys.exit(1)

    img_path = sys.argv[1]
    if not os.path.exists(img_path):
        print(f"❌ 找不到照片：{img_path}")
        sys.exit(1)

    if not os.path.exists(MODEL_FILE):
        print(f"❌ 找不到模型：{MODEL_FILE}")
        print("請先執行：python3 scripts/train_knn.py")
        sys.exit(1)

    results = predict(img_path)

    print("\n" + "="*40)
    if results:
        owners = [r for r in results if r[2]]
        strangers = [r for r in results if not r[2]]
        print(f"總結：{len(owners)} 個認識的人，{len(strangers)} 個陌生人")

if __name__ == "__main__":
    main()

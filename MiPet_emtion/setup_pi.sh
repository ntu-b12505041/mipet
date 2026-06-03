#!/bin/bash
# setup_pi.sh
# 新 Pi 環境一鍵建立腳本
# 執行：bash ~/MiPet/setup_pi.sh

set -e
MIPET_DIR="$HOME/MiPet"
VENV_DIR="$MIPET_DIR/mipet_venv"
PYTHON_VERSION="3.12.9"

echo "=== Step 1: 確認 pyenv ==="
if ! command -v pyenv &> /dev/null; then
    echo "安裝 pyenv..."
    sudo apt-get install -y make build-essential libssl-dev zlib1g-dev \
        libbz2-dev libreadline-dev libsqlite3-dev wget curl llvm \
        libncurses5-dev xz-utils tk-dev libxml2-dev libffi-dev liblzma-dev
    curl https://pyenv.run | bash
    echo 'export PYENV_ROOT="$HOME/.pyenv"' >> ~/.bashrc
    echo 'export PATH="$PYENV_ROOT/bin:$PATH"' >> ~/.bashrc
    echo 'eval "$(pyenv init -)"' >> ~/.bashrc
    source ~/.bashrc
fi

echo "=== Step 2: 安裝 Python $PYTHON_VERSION ==="
pyenv install -s $PYTHON_VERSION
pyenv local $PYTHON_VERSION

echo "=== Step 3: 建立 venv ==="
rm -rf "$VENV_DIR"
python -m venv "$VENV_DIR"
source "$VENV_DIR/bin/activate"

echo "=== Step 4: 安裝套件 ==="
pip install --upgrade pip
pip install -r "$MIPET_DIR/requirements_pi.txt"

echo "=== Step 5: 修復 face_recognition_models ==="
FRM_INIT="$VENV_DIR/lib/python3.12/site-packages/face_recognition_models/__init__.py"
cat > "$FRM_INIT" << 'EOF'
import os as _os

def _model(filename):
    return _os.path.join(_os.path.dirname(__file__), "models", filename)

def pose_predictor_model_location():
    return _model("shape_predictor_68_face_landmarks.dat")

def pose_predictor_five_point_model_location():
    return _model("shape_predictor_5_face_landmarks.dat")

def face_recognition_model_location():
    return _model("dlib_face_recognition_resnet_model_v1.dat")

def cnn_face_detector_model_location():
    return _model("mmod_human_face_detector.dat")
EOF
echo "face_recognition_models 已修復"

echo "=== Step 6: 驗證 ==="
python -c "import face_recognition, mediapipe, paho.mqtt.client, cv2, flask, gpiozero; print('全部 OK')"

echo ""
echo "✅ 設定完成！執行方式："
echo "   source $VENV_DIR/bin/activate"
echo "   python $MIPET_DIR/pi_vision.py"

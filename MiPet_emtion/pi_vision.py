import sys
from unittest.mock import MagicMock
_mock = MagicMock()
sys.modules["kms"]   = _mock
sys.modules["pykms"] = _mock

import os
os.environ["ORT_LOGGING_LEVEL"] = "3"
os.environ["GLOG_minloglevel"] = "3"
import warnings
warnings.filterwarnings("ignore")
import time
import json
import pickle
import argparse
import threading
import numpy as np
import cv2
import face_recognition
import paho.mqtt.client as mqtt
import onnxruntime as ort
from pi_emotion import handle_event as emotion_event, mipet as _emotion_sys
from collections import deque, Counter
from io import BufferedIOBase
from threading import Condition
from flask import Flask, Response, render_template_string

# ── MQTT ─────────────────────────────────────
BROKER     = "broker.emqx.io"
PORT       = 1883
TOPIC_VIS  = "mimicpet/vision"
TOPIC_EVT  = "mimicpet/event"
CLIENT_ID  = "mipet-pi-vision"

# ── TTP223 GPIO ───────────────────────────────
TTP223_PIN = 25

# ── 情緒 → MQTT 事件 ──────────────────────────
EMOTION_TO_MQTT = {
    "happy":    "owner_happy",
    "surprise": "owner_happy",
    "angry":    "owner_stressed",
    "disgust":  "owner_stressed",
    "fear":     "owner_stressed",
    "sad":      "owner_stressed",
    "neutral":  None,
}

# ── 持續情緒判斷秒數 ──────────────────────────
SUSTAINED_SECONDS = 2

# ── Model paths ───────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(BASE_DIR, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

def _find(name):
    local = os.path.join(BASE_DIR, "model", name)
    pc    = os.path.join(BASE_DIR, "..", "model", name)
    return local if os.path.exists(local) else pc

MODEL_FILE        = _find("face_model.pkl")
EMOTION_ONNX_FILE = _find("emotion.onnx")

# ── Cooldowns（秒）────────────────────────────
COOLDOWN_VIS    = 10
DETECT_TIMEOUT  = 60 * 30

# ── Temporal smoothing ────────────────────────
SMOOTH_WINDOW = 10

# ── HTTP stream port ──────────────────────────
HTTP_PORT = 5000

# Owner approach behavior. The motor driver comes from mipet_car, so the
# already-tested TB6612 wiring/config remains the source of truth.
OWNER_APPROACH_SPEED = 0.5
STRANGER_BACK_SPEED = 0.35
STRANGER_BACK_SECONDS = 0.8
OWNER_LOST_STOP_SECONDS = 0.7
OWNER_DEADBAND_RATIO = 0.12
OWNER_MAX_TURN = 0.35
OWNER_TURN_KP = 0.65
DEFAULT_CAMERA_WIDTH = 320
DEFAULT_CAMERA_HEIGHT = 240
DEFAULT_PROCESS_EVERY = 3

TEMPLATE = '''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>🐾 MiPet Live</title>
  <link href="https://fonts.googleapis.com/css2?family=Nunito:wght@400;700;800&display=swap" rel="stylesheet">
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background: linear-gradient(135deg, #fce4ec 0%, #f8bbd0 50%, #e1bee7 100%);
      min-height: 100vh;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      font-family: "Nunito", sans-serif;
      padding: 20px;
    }
    .card {
      background: rgba(255,255,255,0.88);
      border-radius: 28px;
      padding: 24px 24px 18px;
      box-shadow: 0 8px 40px rgba(236,64,122,0.18);
      max-width: 860px;
      width: 100%;
    }
    .header {
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 10px;
      margin-bottom: 10px;
    }
    h1 { color: #e91e63; font-size: 1.9rem; font-weight: 800; letter-spacing: 1px; }
    .top-bar {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 14px;
      gap: 12px;
    }
    .live-badge {
      display: flex;
      align-items: center;
      gap: 6px;
      background: #fff0f5;
      border: 1.5px solid #f48fb1;
      border-radius: 99px;
      padding: 4px 14px;
      font-size: 0.82rem;
      color: #e91e63;
      font-weight: 700;
      white-space: nowrap;
    }
    .dot { width:8px; height:8px; border-radius:50%; background:#e91e63; animation:blink 1.4s infinite; }
    @keyframes blink { 0%,100%{opacity:1} 50%{opacity:0.2} }

    /* ── 狀態卡片 ── */
    .state-card {
      border-radius: 20px;
      padding: 14px 20px 12px;
      margin-bottom: 14px;
      text-align: center;
      transition: background 0.5s ease, color 0.5s ease;
    }
    .state-emoji { font-size: 2.6rem; line-height: 1.1; display: block; }
    .state-name  {
      font-size: 1.7rem; font-weight: 800; letter-spacing: 3px;
      display: block; margin-top: 2px;
    }
    .state-desc  {
      font-size: 0.82rem; font-weight: 700; opacity: 0.75;
      margin-top: 3px; display: block;
    }
    .sc-HAPPY  { background: linear-gradient(135deg,#fff9c4,#ffe082); color:#e65100; }
    .sc-LONELY { background: linear-gradient(135deg,#e3f2fd,#bbdefb); color:#0d47a1; }
    .sc-CARING { background: linear-gradient(135deg,#fce4ec,#f48fb1); color:#880e4f; }
    .sc-IDLE   { background: linear-gradient(135deg,#f3e5f5,#e1bee7); color:#4a148c; }
    @keyframes heartbeat {
      0%,100%{transform:scale(1)} 15%{transform:scale(1.04)} 30%{transform:scale(1)} 45%{transform:scale(1.02)}
    }
    @keyframes breathing {
      0%,100%{opacity:.88;transform:scale(1)} 50%{opacity:1;transform:scale(1.01)}
    }
    @keyframes shimmer {
      0%,100%{filter:brightness(1)} 50%{filter:brightness(1.08)}
    }
    .sc-HAPPY  { animation: shimmer  2s infinite ease-in-out; }
    .sc-CARING { animation: heartbeat 1.3s infinite; }
    .sc-LONELY { animation: breathing 3s infinite ease-in-out; }
    .sc-IDLE   { animation: breathing 5s infinite ease-in-out; }

    /* ── 血條 HUD ── */
    .hud {
      background: rgba(255,245,250,0.85);
      border: 1.5px solid #f8bbd0;
      border-radius: 16px;
      padding: 12px 16px;
      margin-bottom: 14px;
    }
    .bar-row {
      display: flex;
      align-items: center;
      gap: 8px;
      margin-bottom: 7px;
    }
    .bar-row:last-child { margin-bottom: 0; }
    .bar-icon { font-size: 1rem; width: 22px; text-align: center; }
    .bar-label { font-size: 0.78rem; font-weight: 700; width: 76px; color: #555; }
    .bar-track {
      flex: 1;
      height: 14px;
      background: #eeeeee;
      border-radius: 99px;
      overflow: hidden;
      box-shadow: inset 0 1px 3px rgba(0,0,0,0.1);
    }
    .bar-fill {
      height: 100%;
      border-radius: 99px;
      transition: width 0.6s cubic-bezier(.4,0,.2,1);
      position: relative;
    }
    .bar-fill::after {
      content:"";
      position:absolute; top:2px; left:6px; right:6px; height:3px;
      background:rgba(255,255,255,0.45); border-radius:99px;
    }
    .b-happiness { background: linear-gradient(90deg,#f48fb1,#e91e63); }
    .b-loneliness { background: linear-gradient(90deg,#90caf9,#1976d2); }
    .b-trust { background: linear-gradient(90deg,#a5d6a7,#2e7d32); }
    .bar-val { font-size: 0.78rem; font-weight: 800; width: 28px; text-align: right; color:#444; }

    /* ── 鏡頭 ── */
    .stream-wrap {
      border-radius: 18px;
      overflow: hidden;
      border: 3px solid #f48fb1;
      box-shadow: 0 4px 20px rgba(233,30,99,0.12);
    }
    img { display: block; width: 100%; }
    .footer {
      margin-top: 12px;
      text-align: center;
      color: #ce93d8;
      font-size: 0.82rem;
      font-weight: 700;
    }
  </style>
</head>
<body>
  <div class="card">
    <div class="header">
      <span style="font-size:2rem">🐾</span>
      <h1>MiPet Live</h1>
      <span style="font-size:2rem">🐾</span>
    </div>

    <div class="top-bar">
      <div class="live-badge"><span class="dot"></span>&nbsp;LIVE</div>
    </div>

    <div class="state-card sc-IDLE" id="state-card">
      <span class="state-emoji" id="state-emoji">😴</span>
      <span class="state-name"  id="state-name">IDLE</span>
      <span class="state-desc"  id="state-desc">just chillin~ hello there 🌙</span>
    </div>

    <div class="hud">
      <div class="bar-row">
        <span class="bar-icon">❤️</span>
        <span class="bar-label">Happiness</span>
        <div class="bar-track"><div class="bar-fill b-happiness" id="b-happy" style="width:50%"></div></div>
        <span class="bar-val" id="v-happy">50</span>
      </div>
      <div class="bar-row">
        <span class="bar-icon">💙</span>
        <span class="bar-label">Loneliness</span>
        <div class="bar-track"><div class="bar-fill b-loneliness" id="b-lonely" style="width:20%"></div></div>
        <span class="bar-val" id="v-lonely">20</span>
      </div>
      <div class="bar-row">
        <span class="bar-icon">💚</span>
        <span class="bar-label">Trust</span>
        <div class="bar-track"><div class="bar-fill b-trust" id="b-trust" style="width:60%"></div></div>
        <span class="bar-val" id="v-trust">60</span>
      </div>
    </div>

    <div class="stream-wrap">
      <img src="/api/stream" alt="MiPet Camera">
    </div>
    <div class="footer">˚ ༘♡ ◕⩊◕ MiPet is watching over you ◕⩊◕ ♡༘ ˚</div>
  </div>

  <script>
    const STATE_EMOJI = { HAPPY:"✨", LONELY:"💙", CARING:"💗", IDLE:"🌙" };
    const STATE_DESC  = {
      HAPPY:  "yay!! feeling great today ✨",
      LONELY: "missing you... come play with me 💙",
      CARING: "r u ok? i'm worried about u 💗",
      IDLE:   "just chillin~ hello there 🌙"
    };
    const STATE_CLASS = { HAPPY:"sc-HAPPY", LONELY:"sc-LONELY", CARING:"sc-CARING", IDLE:"sc-IDLE" };

    async function update() {
      try {
        const d = await fetch("/api/status").then(r => r.json());
        const v = d.vars, s = d.state;

        document.getElementById("b-happy").style.width  = v.happiness  + "%";
        document.getElementById("b-lonely").style.width = v.loneliness + "%";
        document.getElementById("b-trust").style.width  = v.trust      + "%";
        document.getElementById("v-happy").textContent  = v.happiness;
        document.getElementById("v-lonely").textContent = v.loneliness;
        document.getElementById("v-trust").textContent  = v.trust;

        const card = document.getElementById("state-card");
        card.className = "state-card " + (STATE_CLASS[s] || "sc-IDLE");
        document.getElementById("state-emoji").textContent = STATE_EMOJI[s] || "🌙";
        document.getElementById("state-name").textContent  = s;
        document.getElementById("state-desc").textContent  = STATE_DESC[s] || "";
      } catch(e) {}
    }

    setInterval(update, 1000);
    update();
  </script>
</body>
</html>'''

app = Flask(__name__)


# ─────────────────────────────────────────────
#  StreamingOutput — 與 streamhttp.py 完全相同
# ─────────────────────────────────────────────
class StreamingOutput(BufferedIOBase):
    def __init__(self):
        self.frame = None
        self.condition = Condition()

    def write(self, buf):
        with self.condition:
            self.frame = buf
            self.condition.notify_all()


raw_output = StreamingOutput()
output     = StreamingOutput()


def gen_frames():
    while True:
        with output.condition:
            output.condition.wait()
            frame = output.frame
        yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')


@app.route('/')
def index():
    return render_template_string(TEMPLATE)


@app.route('/api/stream')
def video_stream():
    return Response(gen_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')


@app.route('/api/status')
def api_status():
    return {
        "state": _emotion_sys.engine.get_state(),
        "vars":  _emotion_sys.engine.get_vars(),
    }


# ─────────────────────────────────────────────
#  載入 KNN 人臉辨識模型
# ─────────────────────────────────────────────
def _draw_status_overlay(frame_bgr, vision_event=None, emotion=None, detecting=False, motor_text=""):
    state = _emotion_sys.engine.get_state()
    vars_now = _emotion_sys.engine.get_vars()
    lines = [
        f"STATE: {state}",
        f"Happiness : {vars_now.get('happiness', 0)}",
        f"Loneliness: {vars_now.get('loneliness', 0)}",
        f"Trust     : {vars_now.get('trust', 0)}",
    ]

    x, y = 8, 8
    line_h = 15
    width = 165
    height = 10 + line_h * len(lines)
    overlay = frame_bgr.copy()
    cv2.rectangle(overlay, (x, y), (x + width, y + height), (20, 20, 20), -1)
    cv2.addWeighted(overlay, 0.55, frame_bgr, 0.45, 0, frame_bgr)

    color_by_state = {
        "HAPPY": (0, 255, 255),
        "LONELY": (255, 180, 80),
        "CARING": (180, 120, 255),
        "IDLE": (230, 230, 230),
    }
    for idx, text in enumerate(lines):
        color = color_by_state.get(state, (230, 230, 230)) if idx == 0 else (245, 245, 245)
        cv2.putText(
            frame_bgr,
            text,
            (x + 7, y + 17 + idx * line_h),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.34,
            color,
            1,
            cv2.LINE_AA,
        )
    return frame_bgr


def load_model():
    with open(MODEL_FILE, "rb") as f:
        data = pickle.load(f)
    return data["knn"], data.get("threshold", 0.45), data["k"]


# ─────────────────────────────────────────────
#  Emotion ONNX
# ─────────────────────────────────────────────
EMOTION_LABELS = ["angry", "disgust", "fear", "happy", "neutral", "sad", "surprise"]
_IMG_SIZE      = 260
_MEAN          = np.array([0.485, 0.456, 0.406], dtype=np.float32)
_STD           = np.array([0.229, 0.224, 0.225], dtype=np.float32)

_emotion_session = ort.InferenceSession(
    EMOTION_ONNX_FILE, providers=["CPUExecutionProvider"]
)

def _softmax(x):
    e = np.exp(x - x.max())
    return e / e.sum()

def predict_emotion(face_bgr):
    img    = cv2.resize(face_bgr, (_IMG_SIZE, _IMG_SIZE))
    img    = cv2.cvtColor(img, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
    img    = (img - _MEAN) / _STD
    inp    = img.transpose(2, 0, 1)[np.newaxis].astype(np.float32)
    logits = _emotion_session.run(None, {"input": inp})[0][0]
    probs  = _softmax(logits)
    idx    = int(np.argmax(probs))
    return EMOTION_LABELS[idx], float(probs[idx])


# ─────────────────────────────────────────────
#  MQTT client
# ─────────────────────────────────────────────
def make_mqtt_client():
    class DisabledMqttClient:
        def publish(self, *args, **kwargs):
            return None

        def loop_stop(self):
            return None

        def disconnect(self):
            return None

    try:
        client = mqtt.Client(client_id=CLIENT_ID, protocol=mqtt.MQTTv5)
        client.connect(BROKER, PORT, keepalive=60)
        client.loop_start()
        return client
    except Exception as exc:
        print(f"[Vision] MQTT disabled: {exc}")
        return DisabledMqttClient()


class OwnerApproachController:
    def __init__(
        self,
        enabled=True,
        speed=OWNER_APPROACH_SPEED,
        turn_kp=OWNER_TURN_KP,
        max_turn=OWNER_MAX_TURN,
        deadband_ratio=OWNER_DEADBAND_RATIO,
    ):
        self.enabled = enabled
        self.speed = max(0.0, min(float(speed), 1.0))
        self.turn_kp = max(0.0, float(turn_kp))
        self.max_turn = max(0.0, min(float(max_turn), 1.0))
        self.deadband_ratio = max(0.0, min(float(deadband_ratio), 1.0))
        self.motor = None
        self.moving = False

        if not enabled:
            print("[Approach] Motor approach disabled.")
            return

        try:
            from mipet_car.motor import MotorDriver

            self.motor = MotorDriver(allow_mock_fallback=False)
            print(f"[Approach] Motor ready. Owner approach speed={self.speed:.2f}")
        except Exception as exc:
            self.enabled = False
            print(f"[Approach] Motor unavailable; owner approach disabled: {exc}")

    def approach(self):
        self.follow_owner(None, 0)

    def follow_owner(self, owner_center_x, frame_width):
        if not self.enabled or self.motor is None:
            return
        self.motor.set_speed(self.speed, self.speed)
        if not self.moving:
            print(f"[Approach] owner detected -> forward speed={self.speed:.2f}")
        self.moving = True

    def back_away(self, speed=STRANGER_BACK_SPEED):
        if not self.enabled or self.motor is None:
            return
        speed = max(0.0, min(float(speed), 1.0))
        self.motor.set_speed(-speed, -speed)
        if not self.moving:
            print(f"[Approach] stranger detected -> back away speed={speed:.2f}")
        self.moving = True

    def stop(self, reason=""):
        if self.motor is None:
            return
        self.motor.stop()
        if self.moving:
            suffix = f" ({reason})" if reason else ""
            print(f"[Approach] stop{suffix}")
        self.moving = False

    def close(self):
        if self.motor is None:
            return
        self.stop("shutdown")
        self.motor.close()


# ─────────────────────────────────────────────
#  辨識單一幀
#  detecting=False：只做人臉辨識，不做情緒
#  detecting=True ：人臉辨識 + 情緒偵測
# ─────────────────────────────────────────────
def classify_and_draw(frame_bgr, knn, threshold, k,
                      emotion_history, detecting):
    rgb       = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
    locations = face_recognition.face_locations(rgb, model="hog")

    if not locations:
        return frame_bgr, None, None, None

    encodings    = face_recognition.face_encodings(rgb, locations)
    vision_event = "stranger_seen"
    smoothed_emotion = None
    owner_box    = None
    owner_center_x = None

    for (top, right, bottom, left), enc in zip(locations, encodings):
        distances, _ = knn.kneighbors([enc], n_neighbors=k)
        dist     = float(distances[0][0])
        label    = knn.predict([enc])[0]
        is_owner = dist <= threshold and label != "unknown"

        if is_owner:
            vision_event = "owner_seen"
            color        = (0, 255, 0)
            text         = f"OWNER {dist:.2f}"
            owner_box    = (top, right, bottom, left)
            owner_center_x = (left + right) / 2.0
        else:
            color = (0, 0, 255)
            text  = f"STRANGER {dist:.2f}"

        cv2.rectangle(frame_bgr, (left, top), (right, bottom), color, 2)
        cv2.rectangle(frame_bgr, (left, bottom - 22), (right, bottom), color, cv2.FILLED)
        cv2.putText(frame_bgr, text, (left + 4, bottom - 6),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)

    # ── 情緒偵測：只在 detecting=True 且偵測到 owner 時執行 ──
    if detecting and owner_box is not None:
        try:
            top, right, bottom, left = owner_box
            face_crop = frame_bgr[top:bottom, left:right]
            if face_crop.size > 0:
                emotion, conf = predict_emotion(face_crop)
                emotion_history.append(emotion)
                smoothed_emotion = Counter(emotion_history).most_common(1)[0][0]

                color_map = {
                    "happy": (0, 255, 255), "surprise": (0, 200, 255),
                    "angry": (0, 0, 255),   "disgust":  (0, 0, 200),
                    "fear":  (0, 100, 255), "sad":      (100, 100, 255),
                    "neutral": (200, 200, 200),
                }
                color = color_map.get(smoothed_emotion, (200, 200, 200))
                cv2.putText(frame_bgr,
                            f"{smoothed_emotion.upper()} ({conf:.2f})",
                            (left, top - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.65, color, 2)
        except Exception as e:
            print(f"[Emotion] {e}")
    elif owner_box is not None and not detecting:
        # 等待觸碰中，顯示提示
        top, _, _, left = owner_box
        cv2.putText(frame_bgr, "WAITING TOUCH...",
                    (left, top - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

    return frame_bgr, vision_event, smoothed_emotion, owner_center_x


# ─────────────────────────────────────────────
#  測試模式（不需攝影機，自動跳過觸碰等待）
# ─────────────────────────────────────────────
def run_test(image_path):
    knn, threshold, k = load_model()
    frame = cv2.imread(image_path)
    if frame is None:
        print(f"❌ 找不到圖片：{image_path}")
        return

    history = deque(maxlen=SMOOTH_WINDOW)
    annotated, vision_event, emotion, _ = classify_and_draw(
        frame, knn, threshold, k, history, detecting=True)

    if vision_event is None:
        print("找不到人臉")
    else:
        print(f"vision : {vision_event}")
        if emotion:
            mqtt_evt = EMOTION_TO_MQTT.get(emotion)
            print(f"emotion: {emotion}  →  MQTT: {mqtt_evt or '不發送'}")

    out_path = image_path.rsplit(".", 1)[0] + "_result.jpg"
    cv2.imwrite(out_path, annotated)
    print(f"結果圖片：{out_path}")


# ─────────────────────────────────────────────
#  即時模式
# ─────────────────────────────────────────────
def run_live(
    *,
    approach_speed=OWNER_APPROACH_SPEED,
    motor_enabled=True,
    touch_pin=TTP223_PIN,
    host="0.0.0.0",
    port=HTTP_PORT,
    width=DEFAULT_CAMERA_WIDTH,
    height=DEFAULT_CAMERA_HEIGHT,
    process_every=DEFAULT_PROCESS_EVERY,
    vflip=False,
    hflip=False,
    owner_turn_kp=OWNER_TURN_KP,
    owner_max_turn=OWNER_MAX_TURN,
    owner_deadband_ratio=OWNER_DEADBAND_RATIO,
):
    from gpiozero import Button, Device
    from gpiozero.pins.lgpio import LGPIOFactory
    from picamera2 import Picamera2

    Device.pin_factory = LGPIOFactory()   # kernel 6.x 需要 lgpio 後端
    from picamera2.encoders import JpegEncoder, Quality
    from picamera2.outputs import FileOutput
    from libcamera import Transform

    # ── TTP223 設定（gpiozero）────────────────
    detecting         = False
    detect_start_time = None
    touch_lock        = threading.Lock()
    approach          = OwnerApproachController(
        enabled=motor_enabled,
        speed=approach_speed,
        turn_kp=owner_turn_kp,
        max_turn=owner_max_turn,
        deadband_ratio=owner_deadband_ratio,
    )

    def on_touch():
        nonlocal detecting, detect_start_time
        approach.stop("touch sensor pressed")
        # 每次觸碰都立即更新情緒變數（無冷卻）
        mqtt_client.publish(TOPIC_EVT, json.dumps({"event": "touched"}))
        emotion_event("touched")
        with touch_lock:
            if not detecting:
                detecting         = True
                detect_start_time = time.time()
                print("[Touch] TTP223 觸碰！開始情緒偵測")
            else:
                print("[Touch] TTP223 觸碰！情緒變數已更新")

    ttp223 = Button(touch_pin, pull_up=False)
    ttp223.when_pressed = on_touch

    # ── 載入模型與攝影機 ──────────────────────
    knn, threshold, k = load_model()
    mqtt_client = make_mqtt_client()
    print(f"[Vision] MQTT 連線到 {BROKER}")

    cam = Picamera2()
    process_every = max(1, int(process_every))
    config = cam.create_video_configuration(
        {'size': (int(width), int(height)), 'format': 'XBGR8888'},
        transform=Transform(vflip=int(vflip), hflip=int(hflip)),
        controls={'NoiseReductionMode': 2, 'Sharpness': 1.5}
    )
    cam.configure(config)
    cam.start_recording(JpegEncoder(), FileOutput(raw_output), Quality.MEDIUM)
    print(
        f"[Vision] camera started {width}x{height}, process_every={process_every}, "
        f"vflip={vflip}, hflip={hflip}. Open http://<Pi IP>:{port}"
    )

    flask_thread = threading.Thread(
        target=lambda: app.run(host=host, port=port, threaded=True),
        daemon=True
    )
    flask_thread.start()

    last_vis_sent: dict[str, float] = {}
    emotion_history  = deque(maxlen=SMOOTH_WINDOW)
    last_owner_seen   = 0.0
    frame_index       = 0
    last_annotated    = None
    last_vision_event = None
    last_emotion      = None
    last_owner_center_x = None
    stranger_back_until = 0.0
    last_lcd_emotion = None

    # ── 持續情緒追蹤變數 ──────────────────────
    sustained_mqtt_evt = None   # 目前追蹤中的 MQTT 事件
    sustained_start    = None   # 該情緒開始持續的時間

    try:
        while True:
            with raw_output.condition:
                raw_output.condition.wait()
                data = raw_output.frame
            if data is None:
                continue

            frame = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
            if frame is None:
                continue

            with touch_lock:
                cur_detecting = detecting

            frame_index += 1
            should_process = last_annotated is None or frame_index % process_every == 0

            if should_process:
                annotated, vision_event, smoothed_emotion, owner_center_x = classify_and_draw(
                    frame, knn, threshold, k, emotion_history, cur_detecting)
                last_annotated = annotated
                last_vision_event = vision_event
                last_emotion = smoothed_emotion
                last_owner_center_x = owner_center_x
            else:
                annotated = last_annotated
                vision_event = last_vision_event
                smoothed_emotion = last_emotion if cur_detecting else None
                owner_center_x = last_owner_center_x

            now = time.time()

            # ── mimicpet/vision（owner/stranger，有冷卻）──
            if vision_event:
                if now - last_vis_sent.get(vision_event, 0) >= COOLDOWN_VIS:
                    mqtt_client.publish(TOPIC_VIS, json.dumps({"event": vision_event}))
                    last_vis_sent[vision_event] = now
                    print(f"[Vision] {vision_event}")

            if vision_event == "owner_seen":
                last_owner_seen = now
                stranger_back_until = 0.0
                if cur_detecting:
                    approach.stop("emotion detection active")
                else:
                    approach.follow_owner(owner_center_x, frame.shape[1])
            elif vision_event == "stranger_seen" and not cur_detecting:
                stranger_back_until = now + STRANGER_BACK_SECONDS
                approach.back_away(STRANGER_BACK_SPEED)
            elif cur_detecting:
                approach.stop("emotion detection active")
            elif now < stranger_back_until:
                approach.back_away(STRANGER_BACK_SPEED)
            elif now - last_owner_seen >= OWNER_LOST_STOP_SECONDS:
                approach.stop("owner lost")

            # ── 情緒持續判斷邏輯 ─────────────────
            if cur_detecting and smoothed_emotion is not None:
                if smoothed_emotion != last_lcd_emotion:
                    _emotion_sys.show_emotion(smoothed_emotion)
                    last_lcd_emotion = smoothed_emotion

                mqtt_evt = EMOTION_TO_MQTT.get(smoothed_emotion)

                if mqtt_evt is None:
                    # neutral：重置計時
                    sustained_mqtt_evt = None
                    sustained_start    = None

                    # 逾時檢查（30 分鐘）
                    with touch_lock:
                        if detect_start_time and (now - detect_start_time) >= DETECT_TIMEOUT:
                            detecting         = False
                            detect_start_time = None
                            emotion_history.clear()
                            _emotion_sys.refresh_state_display()
                            last_lcd_emotion = None
                            print("[Touch] 偵測逾時（30 分鐘），停止偵測")

                elif mqtt_evt != sustained_mqtt_evt:
                    # 情緒改變：重置計時
                    sustained_mqtt_evt = mqtt_evt
                    sustained_start    = now
                    print(f"[Emotion] 開始追蹤 {mqtt_evt}")

                else:
                    # 同一情緒，累計時間
                    elapsed = now - sustained_start
                    print(f"[Emotion] {mqtt_evt} 持續 {elapsed:.1f}s / {SUSTAINED_SECONDS}s")

                    if elapsed >= SUSTAINED_SECONDS:
                        # 持續 10 秒，發布並停止偵測
                        mqtt_client.publish(TOPIC_EVT, json.dumps({"event": mqtt_evt}))
                        print(f"[Emotion] ✅ {mqtt_evt} 確認，停止偵測")
                        emotion_event(mqtt_evt)

                        with touch_lock:
                            detecting = False
                        sustained_mqtt_evt = None
                        sustained_start    = None
                        emotion_history.clear()
                        _emotion_sys.refresh_state_display()
                        last_lcd_emotion = None

            stream_frame = annotated.copy()
            if vision_event == "owner_seen" and not cur_detecting:
                motor_text = f"forward {approach.speed:.2f}"
            elif vision_event == "stranger_seen" and not cur_detecting:
                motor_text = f"back {STRANGER_BACK_SPEED:.2f}"
            elif cur_detecting:
                motor_text = "stop/emotion"
            else:
                motor_text = "stop"
            _draw_status_overlay(
                stream_frame,
                vision_event=vision_event,
                emotion=smoothed_emotion,
                detecting=cur_detecting,
                motor_text=motor_text,
            )
            _, jpeg = cv2.imencode('.jpg', stream_frame)
            output.write(jpeg.tobytes())

    except KeyboardInterrupt:
        print("\n[Vision] 停止")
    finally:
        approach.close()
        cam.stop()
        ttp223.close()
        mqtt_client.loop_stop()
        mqtt_client.disconnect()


# ─────────────────────────────────────────────
#  Entry point
# ─────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MiPet 人臉辨識模組")
    parser.add_argument("--test", metavar="IMAGE", help="測試模式：傳入圖片路徑")
    parser.add_argument("--approach-speed", type=float, default=OWNER_APPROACH_SPEED)
    parser.add_argument("--no-motor", action="store_true", help="Disable owner approach motor control.")
    parser.add_argument("--touch-pin", type=int, default=TTP223_PIN)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=HTTP_PORT)
    parser.add_argument("--width", type=int, default=DEFAULT_CAMERA_WIDTH)
    parser.add_argument("--height", type=int, default=DEFAULT_CAMERA_HEIGHT)
    parser.add_argument(
        "--process-every",
        type=int,
        default=DEFAULT_PROCESS_EVERY,
        help="Run face/emotion recognition once every N camera frames.",
    )
    parser.add_argument("--vflip", action="store_true", help="Flip camera vertically.")
    parser.add_argument("--hflip", action="store_true", help="Flip camera horizontally.")
    parser.add_argument("--owner-turn-kp", type=float, default=OWNER_TURN_KP)
    parser.add_argument("--owner-max-turn", type=float, default=OWNER_MAX_TURN)
    parser.add_argument("--owner-deadband-ratio", type=float, default=OWNER_DEADBAND_RATIO)
    args = parser.parse_args()

    if args.test:
        run_test(args.test)
    else:
        run_live(
            approach_speed=args.approach_speed,
            motor_enabled=not args.no_motor,
            touch_pin=args.touch_pin,
            host=args.host,
            port=args.port,
            width=args.width,
            height=args.height,
            process_every=args.process_every,
            vflip=args.vflip,
            hflip=args.hflip,
            owner_turn_kp=args.owner_turn_kp,
            owner_max_turn=args.owner_max_turn,
            owner_deadband_ratio=args.owner_deadband_ratio,
        )

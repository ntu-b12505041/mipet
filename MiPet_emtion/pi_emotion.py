import time
import json
import threading
import os

try:
    import paho.mqtt.client as mqtt
except Exception as exc:
    mqtt = None
    MQTT_IMPORT_ERROR = exc
else:
    MQTT_IMPORT_ERROR = None

try:
    from RPLCD.i2c import CharLCD
except Exception as exc:
    CharLCD = None
    LCD_IMPORT_ERROR = exc
else:
    LCD_IMPORT_ERROR = None

# ── MQTT ──────────────────────────────────────────────
BROKER    = "broker.emqx.io"
PORT      = 1883
TOPIC_EVT = "mimicpet/event"
CLIENT_ID = "mipet-pi-emotion"

# ── LCD ───────────────────────────────────────────────
LCD_ADDR = 0x27
LCD_ADDR_CANDIDATES = (0x27, 0x3F)

# ── 情緒變數預設值 ────────────────────────────────────
DEFAULTS = {"happiness": 50, "loneliness": 20, "trust": 60}

# ── 時間常數 ──────────────────────────────────────────
IDLE_DECAY_INTERVAL = 60         # 每分鐘衰減一次
CARING_DURATION     = 5  * 60   # CARING 狀態持續 5 分鐘後重新計算


# ── CGRAM 字元定義 ────────────────────────────────────
HEART          = (0b00000, 0b01010, 0b11111, 0b11111, 0b01110, 0b00100, 0b00000, 0b00000)
STAR           = (0b00100, 0b00100, 0b10101, 0b01110, 0b11111, 0b01110, 0b10101, 0b00000)
EYE_LEFT_OPEN  = (0b01110, 0b11111, 0b11011, 0b11111, 0b11111, 0b01110, 0b00000, 0b00000)
EYE_RIGHT_OPEN = (0b01110, 0b11111, 0b11011, 0b11111, 0b11111, 0b01110, 0b00000, 0b00000)
EYE_LEFT_BLINK = (0b00000, 0b00000, 0b11111, 0b00000, 0b00000, 0b00000, 0b00000, 0b00000)
EYE_RIGHT_BLINK= (0b00000, 0b00000, 0b11111, 0b00000, 0b00000, 0b00000, 0b00000, 0b00000)
MOUTH_HAPPY    = (0b00000, 0b00000, 0b10001, 0b01010, 0b00100, 0b00000, 0b00000, 0b00000)
MOUTH_SAD      = (0b00000, 0b00000, 0b00100, 0b01010, 0b10001, 0b00000, 0b00000, 0b00000)


# ═══════════════════════════════════════════════════════
#  LCDController：背景執行緒負責動態表情
# ═══════════════════════════════════════════════════════
class LCDController:

    def __init__(self, addr=LCD_ADDR):
        self.lcd = self._create_lcd(addr)
        self._stop = threading.Event()
        self._thread = None
        self._lock   = threading.Lock()

    def _create_lcd(self, addr):
        if CharLCD is None:
            if os.getenv("MIPET_ALLOW_CONSOLE_LCD") == "1":
                print(f"[LCD] RPLCD unavailable, using console display: {LCD_IMPORT_ERROR}")
                return ConsoleLCD()
            raise RuntimeError(
                "LCD is required but RPLCD is unavailable. "
                "Install/check RPLCD, enable I2C, then rerun. "
                f"Original error: {LCD_IMPORT_ERROR}"
            )
        last_error = None
        candidates = [addr] + [candidate for candidate in LCD_ADDR_CANDIDATES if candidate != addr]
        for candidate in candidates:
            try:
                lcd = CharLCD('PCF8574', candidate, port=1, cols=16, rows=2)
                print(f"[LCD] connected at I2C address 0x{candidate:02X}")
                return lcd
            except FileNotFoundError as exc:
                last_error = exc
                break
            except Exception as exc:
                last_error = exc

        if last_error is not None:
            if os.getenv("MIPET_ALLOW_CONSOLE_LCD") == "1":
                print(f"[LCD] LCD init failed, using console display: {last_error}")
                return ConsoleLCD()
            raise RuntimeError(
                "LCD is required but initialization failed. Check wiring: "
                "LCD VCC->5V, GND->GND, SDA->GPIO2/pin3, SCL->GPIO3/pin5, "
                "enable I2C, and confirm address 0x27 or 0x3F with i2cdetect. "
                f"Original error: {last_error}"
            )
        raise RuntimeError("LCD is required but initialization failed for an unknown reason.")

    def set_state(self, state: str):
        with self._lock:
            if self._thread and self._thread.is_alive():
                self._stop.set()
                self._thread.join(timeout=1)
            self._stop.clear()
            fn = {
                "HAPPY":  self._anim_happy,
                "LONELY": self._anim_lonely,
                "CARING": self._anim_caring,
                "IDLE":   self._anim_idle,
            }.get(state, self._anim_idle)
            self._thread = threading.Thread(target=fn, daemon=True)
            self._thread.start()

    def show_emotion(self, emotion: str):
        """Display the currently recognized facial emotion on the rear LCD."""
        with self._lock:
            if self._thread and self._thread.is_alive():
                self._stop.set()
                self._thread.join(timeout=1)
            self._stop.clear()
            fn = {
                "happy": self._show_happy_face,
                "surprise": self._show_surprise_face,
                "angry": self._show_angry_face,
                "disgust": self._show_angry_face,
                "fear": self._show_worried_face,
                "sad": self._show_sad_face,
                "neutral": self._show_neutral_face,
            }.get(emotion, self._show_neutral_face)
            self._thread = threading.Thread(target=fn, daemon=True)
            self._thread.start()

    def _load_chars(self):
        self.lcd.create_char(0, HEART)
        self.lcd.create_char(1, STAR)
        self.lcd.create_char(2, EYE_LEFT_OPEN)
        self.lcd.create_char(3, EYE_RIGHT_OPEN)
        self.lcd.create_char(4, EYE_LEFT_BLINK)
        self.lcd.create_char(5, EYE_RIGHT_BLINK)
        self.lcd.create_char(6, MOUTH_HAPPY)
        self.lcd.create_char(7, MOUTH_SAD)

    def _w(self, row: int, text: str):
        self.lcd.cursor_pos = (row, 0)
        self.lcd.write_string(text.ljust(16)[:16])

    def _c(self, idx: int) -> str:
        return chr(idx)

    def _show_static_face(self, face_line: str, text_line: str):
        self._load_chars()
        self.lcd.clear()
        while not self._stop.is_set():
            self._w(0, face_line)
            self._w(1, text_line)
            if self._stop.wait(0.25):
                break

    def _show_happy_face(self):
        le = self._c(2); re = self._c(3); h = self._c(0); m = self._c(6)
        self._show_static_face(f" {h}{h} ={le}{m}{re}= {h}{h}", " emotion:HAPPY ")

    def _show_sad_face(self):
        le = self._c(2); re = self._c(3); m = self._c(7)
        self._show_static_face(f"    ={le}{m}{re}=    ", " emotion:SAD   ")

    def _show_angry_face(self):
        angry_eye = (0b10000, 0b01000, 0b01110, 0b11111, 0b11011, 0b11111, 0b01110, 0b00000)
        self._load_chars()
        self.lcd.create_char(2, angry_eye)
        self.lcd.create_char(3, angry_eye)
        le = self._c(2); re = self._c(3); m = self._c(7)
        self._show_static_face(f"    ={le}{m}{re}=    ", " emotion:ANGRY ")

    def _show_worried_face(self):
        le = self._c(2); re = self._c(3); m = self._c(7)
        self._show_static_face(f"   .={le}{m}{re}=.   ", " emotion:FEAR  ")

    def _show_surprise_face(self):
        mouth_o = (0b00000, 0b01110, 0b10001, 0b10001, 0b10001, 0b01110, 0b00000, 0b00000)
        self._load_chars()
        self.lcd.create_char(6, mouth_o)
        le = self._c(2); re = self._c(3); m = self._c(6); s = self._c(1)
        self._show_static_face(f" {s}  ={le}{m}{re}=  {s}", " emotion:WOW!  ")

    def _show_neutral_face(self):
        mouth_flat = (0b00000, 0b00000, 0b00000, 0b11111, 0b00000, 0b00000, 0b00000, 0b00000)
        self._load_chars()
        self.lcd.create_char(6, mouth_flat)
        le = self._c(2); re = self._c(3); m = self._c(6)
        self._show_static_face(f"    ={le}{m}{re}=    ", " emotion:OK    ")

    # ── HAPPY：閉嘴微笑 ↔ 張嘴大笑，♡ ↔ ★ ───────────
    def _anim_happy(self):
        MOUTH_OPEN = (0b00000, 0b10001, 0b01110, 0b11111, 0b01110, 0b00000, 0b00000, 0b00000)
        self._load_chars()
        self.lcd.clear()
        le = self._c(2); re = self._c(3)
        h  = self._c(0); s  = self._c(1); m = self._c(6)

        while not self._stop.is_set():
            self.lcd.create_char(6, MOUTH_HAPPY)
            self._w(0, f"{h}{h} ={le}{m}{re}= {h}{h}")
            self._w(1, "   yay!! :D   ")
            if self._stop.wait(0.5): break

            self.lcd.create_char(6, MOUTH_OPEN)
            self._w(0, f"{s}{s} ={le}{m}{re}= {s}{s}")
            self._w(1, "   yay!! :D   ")
            if self._stop.wait(0.5): break

        self.lcd.create_char(6, MOUTH_HAPPY)

    # ── LONELY：眼淚落下 + 緩慢眨眼 ──────────────────
    def _anim_lonely(self):
        TEARS = [
            (0b00100, 0b00110, 0b00000, 0b00000, 0b00000, 0b00000, 0b00000, 0b00000),
            (0b00000, 0b00100, 0b00110, 0b00011, 0b00000, 0b00000, 0b00000, 0b00000),
            (0b00000, 0b00000, 0b00100, 0b00110, 0b00011, 0b00001, 0b00000, 0b00000),
            (0b00000, 0b00000, 0b00000, 0b00000, 0b00000, 0b00000, 0b00000, 0b00000),
        ]
        self._load_chars()
        self.lcd.create_char(0, TEARS[0])
        self.lcd.clear()
        le = self._c(2); re = self._c(3)
        lb = self._c(4); rb = self._c(5)
        ms = self._c(7); tear = self._c(0)

        FACE_OPEN  = f"  ={tear}{le}{ms}{re}{tear}=  "
        FACE_BLINK = f"  ={tear}{lb}{ms}{rb}{tear}=  "

        tear_frame = 0
        tear_next  = time.time() + 1.5
        blink_at   = time.time() + 3.5

        while not self._stop.is_set():
            now = time.time()
            if now >= tear_next:
                tear_frame = (tear_frame + 1) % len(TEARS)
                self.lcd.create_char(0, TEARS[tear_frame])
                tear_next = now + (2.0 if tear_frame == 0 else 0.4)
            if now >= blink_at:
                self._w(0, FACE_BLINK)
                self._w(1, "  miss u...   ")
                if self._stop.wait(0.5): break
                blink_at = time.time() + 3.5
            else:
                self._w(0, FACE_OPEN)
                self._w(1, "  miss u...   ")
            time.sleep(0.08)

        self.lcd.create_char(0, HEART)

    # ── CARING：♡ 脈動 ────────────────────────────────
    def _anim_caring(self):
        self._load_chars()
        self.lcd.clear()
        le = self._c(2); re = self._c(3)
        h  = self._c(0); m  = self._c(6)

        while not self._stop.is_set():
            self._w(0, f" {h}{h} ={le}{m}{re}= {h}{h}")
            self._w(1, "  r u ok? :/  ")
            if self._stop.wait(0.8): break

            self._w(0, f"  {h} ={le}{m}{re}= {h}  ")
            self._w(1, "  r u ok? :/  ")
            if self._stop.wait(0.8): break

    # ── IDLE：平嘴角 + 眨眼 ───────────────────────────
    def _anim_idle(self):
        MOUTH_FLAT = (0b00000, 0b00000, 0b00000, 0b11111, 0b00000, 0b00000, 0b00000, 0b00000)
        self._load_chars()
        self.lcd.create_char(6, MOUTH_FLAT)
        self.lcd.clear()
        le = self._c(2); re = self._c(3)
        lb = self._c(4); rb = self._c(5)
        h  = self._c(0); s  = self._c(1); m = self._c(6)

        blink_at = time.time() + 1.2
        while not self._stop.is_set():
            now = time.time()
            if now >= blink_at:
                self._w(0, f" {s}{h} ={lb}{m}{rb}= {h}{s}")
                self._w(1, "     Hello      ")
                if self._stop.wait(0.2): break
                self._w(0, f" {s}{h} ={le}{m}{re}= {h}{s}")
                self._w(1, "     Hello      ")
                if self._stop.wait(0.2): break
                blink_at = time.time() + 1.2
            else:
                self._w(0, f" {s}{h} ={le}{m}{re}= {h}{s}")
                self._w(1, "     Hello      ")
                time.sleep(0.08)

        self.lcd.create_char(6, MOUTH_HAPPY)

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=1)
        self.lcd.clear()


class ConsoleLCD:
    """Minimal LCD fallback so emotion logic still runs while LCD is absent."""

    def __init__(self):
        self.cursor_pos = (0, 0)

    def create_char(self, idx, data):
        return None

    def clear(self):
        print("[LCD] clear")

    def write_string(self, text):
        row, _ = self.cursor_pos
        print(f"[LCD:{row}] {text}")


# ═══════════════════════════════════════════════════════
#  EmotionEngine：3 個情緒變數 + 狀態機
# ═══════════════════════════════════════════════════════
class EmotionEngine:

    def __init__(self):
        self.vars   = DEFAULTS.copy()
        self._state = "IDLE"
        self._last_interaction = time.time()
        self._lock  = threading.Lock()

    def handle_event(self, event: str) -> str:
        with self._lock:
            e = self.vars

            if event == "touched":
                e["happiness"]  = min(100, e["happiness"]  + 15)
                e["loneliness"] = max(0,   e["loneliness"] - 10)
                e["trust"]      = min(100, e["trust"]       + 5)
                self._last_interaction = time.time()

            elif event == "owner_happy":
                e["happiness"] = min(100, e["happiness"] + 10)
                self._last_interaction = time.time()

            elif event == "owner_stressed":
                # 最高優先：直接觸發 CARING，5 分鐘後自動重新計算
                self._state = "CARING"
                threading.Timer(CARING_DURATION, self._exit_caring).start()
                return "CARING"

            elif event == "idle_too_long":
                e["happiness"]  = max(0,   e["happiness"]  - 10)
                e["loneliness"] = min(100, e["loneliness"] + 20)
                e["trust"]      = max(0,   e["trust"]       - 5)

            self._state = self._compute_state()
            return self._state

    def _exit_caring(self):
        with self._lock:
            if self._state == "CARING":
                self._state = self._compute_state()

    def _compute_state(self) -> str:
        e = self.vars
        if e["loneliness"] > 70 or e["trust"] < 40:
            return "LONELY"
        if e["happiness"] > 75:
            return "HAPPY"
        return "IDLE"

    def get_state(self) -> str:
        return self._state

    def get_vars(self) -> dict:
        with self._lock:
            return self.vars.copy()


# ═══════════════════════════════════════════════════════
#  MiPetEmotion：整合情緒引擎 + LCD + MQTT 同步
# ═══════════════════════════════════════════════════════
class MiPetEmotion:

    def __init__(self):
        self.engine  = EmotionEngine()
        self.display = LCDController()
        self._prev_state = None

        if mqtt is None:
            print(f"[Emotion] MQTT 套件 unavailable: {MQTT_IMPORT_ERROR}（LINE 推播停用，LCD 正常運作）")
            self._mqtt    = None
            self._mqtt_ok = False
        else:
            try:
                self._mqtt = mqtt.Client(client_id=CLIENT_ID, protocol=mqtt.MQTTv5)
                self._mqtt.connect(BROKER, PORT, keepalive=60)
                self._mqtt.loop_start()
                self._mqtt_ok = True
            except Exception as e:
                print(f"[Emotion] MQTT 連線失敗: {e}（LINE 推播停用，LCD 正常運作）")
                self._mqtt    = None
                self._mqtt_ok = False

        # 每小時衰減計時器
        self._decay_thread = threading.Thread(target=self._decay_loop, daemon=True)
        self._decay_thread.start()

        self._apply_state("IDLE")

    def handle_event(self, event: str):
        new_state = self.engine.handle_event(event)
        print(f"[Emotion] {event} → {new_state} | {self.engine.get_vars()}")

        # 同步到雲端 Flask（LINE 推播由雲端負責）
        if self._mqtt_ok:
            self._mqtt.publish(TOPIC_EVT, json.dumps({"event": event}))

        self._apply_state(new_state)

    def show_emotion(self, emotion: str):
        self.display.show_emotion(emotion)

    def refresh_state_display(self):
        self._prev_state = None
        self._apply_state(self.engine.get_state())

    def _apply_state(self, state: str):
        if state != self._prev_state:
            self.display.set_state(state)
            self._prev_state = state

    def _decay_loop(self):
        while True:
            time.sleep(IDLE_DECAY_INTERVAL)
            self.handle_event("idle_too_long")

    def stop(self):
        if self._mqtt:
            self._mqtt.loop_stop()
            self._mqtt.disconnect()
        self.display.stop()


# ── 全域單例，供 pi_vision.py 直接 import 使用 ────────
mipet = MiPetEmotion()

def handle_event(event: str):
    mipet.handle_event(event)

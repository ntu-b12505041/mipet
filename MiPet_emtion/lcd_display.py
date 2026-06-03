"""
pi/lcd_display.py
LCD 1602 自訂字元 + 動畫顯示

模仿 ˚ ༘♡ ⋆｡˚◕⩊◕˚ ༘♡ ⋆｡˚ 的效果
Row 1：表情動畫
Row 2：狀態文字

使用 8 個自訂字元：♡ ★ 貓臉左眼 貓臉右眼 眨眼左 眨眼右 嘴開心 嘴難過
"""

import time
from RPLCD.i2c import CharLCD

# ── LCD 初始化 ──────────────────────────────────────────
lcd = CharLCD(
    i2c_expander='PCF8574',
    address=0x27,
    port=1,
    cols=16,
    rows=2,
    dotsize=8,
)

# ── 自訂字元定義（5×8 像素）────────────────────────────

HEART = (
    0b00000,
    0b01010,
    0b11111,
    0b11111,
    0b01110,
    0b00100,
    0b00000,
    0b00000,
)

STAR = (
    0b00100,
    0b00100,
    0b10101,
    0b01110,
    0b11111,
    0b01110,
    0b10101,
    0b00000,
)

EYE_LEFT_OPEN = (
    0b01110,
    0b11111,
    0b11011,
    0b11111,
    0b11111,
    0b01110,
    0b00000,
    0b00000,
)

EYE_RIGHT_OPEN = (
    0b01110,
    0b11111,
    0b11011,
    0b11111,
    0b11111,
    0b01110,
    0b00000,
    0b00000,
)

EYE_LEFT_BLINK = (
    0b00000,
    0b00000,
    0b11111,
    0b00000,
    0b00000,
    0b00000,
    0b00000,
    0b00000,
)

EYE_RIGHT_BLINK = (
    0b00000,
    0b00000,
    0b11111,
    0b00000,
    0b00000,
    0b00000,
    0b00000,
    0b00000,
)

MOUTH_HAPPY = (
    0b00000,
    0b00000,
    0b10001,
    0b01010,
    0b00100,
    0b00000,
    0b00000,
    0b00000,
)

MOUTH_SAD = (
    0b00000,
    0b00000,
    0b00100,
    0b01010,
    0b10001,
    0b00000,
    0b00000,
    0b00000,
)

# ── 載入字元 ────────────────────────────────────────────
def load_chars():
    lcd.create_char(0, HEART)
    lcd.create_char(1, STAR)
    lcd.create_char(2, EYE_LEFT_OPEN)
    lcd.create_char(3, EYE_RIGHT_OPEN)
    lcd.create_char(4, EYE_LEFT_BLINK)
    lcd.create_char(5, EYE_RIGHT_BLINK)
    lcd.create_char(6, MOUTH_HAPPY)
    lcd.create_char(7, MOUTH_SAD)

# ── 工具 ────────────────────────────────────────────────
def write_line(row: int, text: str):
    lcd.cursor_pos = (row, 0)
    lcd.write_string(text.ljust(16)[:16])

def c(idx: int) -> str:
    return chr(idx)

# ── 動畫 ────────────────────────────────────────────────

def animate_idle(cycles: int = 3):
    """★♡ =◕__◕= ♡★  平嘴角 + 眨眼"""
    MOUTH_FLAT = (0b00000, 0b00000, 0b00000, 0b11111, 0b00000, 0b00000, 0b00000, 0b00000)
    lcd.create_char(6, MOUTH_FLAT)   # 暫時覆蓋 slot 6 為平嘴角

    left_eye_open   = c(2)
    right_eye_open  = c(3)
    left_eye_blink  = c(4)
    right_eye_blink = c(5)
    heart = c(0)
    star  = c(1)
    mouth = c(6)

    for _ in range(cycles):
        write_line(0, f" {star}{heart} ={left_eye_open}{mouth}{right_eye_open}= {heart}{star}")
        write_line(1, "  hello!! ^-^  ")
        time.sleep(1.2)

        write_line(0, f" {star}{heart} ={left_eye_blink}{mouth}{right_eye_blink}= {heart}{star}")
        write_line(1, "  hello!! ^-^  ")
        time.sleep(0.2)

        write_line(0, f" {star}{heart} ={left_eye_open}{mouth}{right_eye_open}= {heart}{star}")
        write_line(1, "  hello!! ^-^  ")
        time.sleep(0.2)

    lcd.create_char(6, MOUTH_HAPPY)  # 還原


def animate_happy(cycles: int = 3):
    """♡♡ =◕⩊◕= ♡♡  閉嘴笑 ↔ 張嘴大笑"""
    MOUTH_OPEN = (0b00000, 0b10001, 0b01110, 0b11111, 0b01110, 0b00000, 0b00000, 0b00000)

    left_eye_open  = c(2)
    right_eye_open = c(3)
    heart = c(0)
    star  = c(1)
    mouth = c(6)

    for _ in range(cycles):
        # 閉嘴微笑 + 愛心
        lcd.create_char(6, MOUTH_HAPPY)
        write_line(0, f"{heart}{heart} ={left_eye_open}{mouth}{right_eye_open}= {heart}{heart}")
        write_line(1, "   yay!! :D   ")
        time.sleep(0.5)

        # 張嘴大笑 + 星星
        lcd.create_char(6, MOUTH_OPEN)
        write_line(0, f"{star}{star} ={left_eye_open}{mouth}{right_eye_open}= {star}{star}")
        write_line(1, "   yay!! :D   ")
        time.sleep(0.5)

    lcd.create_char(6, MOUTH_HAPPY)  # 還原


def animate_lonely(cycles: int = 2):
    """. =◕sad◕= .  眼淚落下 + 緩慢眨眼"""
    left_eye_open   = c(2)
    right_eye_open  = c(3)
    left_eye_blink  = c(4)
    right_eye_blink = c(5)
    mouth_sad = c(7)
    tear      = c(0)   # 借用 HEART slot，LONELY 不需要愛心

    TEARS = [
        (0b00100, 0b00110, 0b00000, 0b00000, 0b00000, 0b00000, 0b00000, 0b00000),  # 高
        (0b00000, 0b00100, 0b00110, 0b00011, 0b00000, 0b00000, 0b00000, 0b00000),  # 中
        (0b00000, 0b00000, 0b00100, 0b00110, 0b00011, 0b00001, 0b00000, 0b00000),  # 低
        (0b00000, 0b00000, 0b00000, 0b00000, 0b00000, 0b00000, 0b00000, 0b00000),  # 消失
    ]
    lcd.create_char(0, TEARS[0])

    FACE_OPEN  = f"  ={tear}{left_eye_open}{mouth_sad}{right_eye_open}{tear}=  "
    FACE_BLINK = f"  ={tear}{left_eye_blink}{mouth_sad}{right_eye_blink}{tear}=  "

    for _ in range(cycles):
        tear_frame = 0
        tear_next  = time.time() + 1.5
        t          = time.time()

        while time.time() < t + 3.5:
            now = time.time()
            if now >= tear_next:
                tear_frame = (tear_frame + 1) % len(TEARS)
                lcd.create_char(0, TEARS[tear_frame])
                tear_next = now + (2.0 if tear_frame == 0 else 0.4)
            write_line(0, FACE_OPEN)
            write_line(1, "  miss u...   ")
            time.sleep(0.08)

        # 緩慢眨眼
        write_line(0, FACE_BLINK)
        write_line(1, "  miss u...   ")
        time.sleep(0.5)

    lcd.create_char(0, HEART)   # 還原 HEART


def animate_caring(cycles: int = 2):
    """♡ =◕⩊◕= ♡  愛心脈動"""
    left_eye_open  = c(2)
    right_eye_open = c(3)
    heart = c(0)
    mouth = c(6)

    for _ in range(cycles):
        write_line(0, f" {heart}{heart} ={left_eye_open}{mouth}{right_eye_open}= {heart}{heart}")
        write_line(1, "  r u ok? :/  ")
        time.sleep(0.8)

        write_line(0, f"  {heart} ={left_eye_open}{mouth}{right_eye_open}= {heart}  ")
        write_line(1, "  r u ok? :/  ")
        time.sleep(0.8)


# ── 狀態對應 ────────────────────────────────────────────
STATE_ANIMATIONS = {
    "IDLE":   animate_idle,
    "HAPPY":  animate_happy,
    "LONELY": animate_lonely,
    "CARING": animate_caring,
}

def display_state(state: str, cycles: int = 3):
    anim = STATE_ANIMATIONS.get(state, animate_idle)
    anim(cycles)


# ── 測試主程式 ───────────────────────────────────────────
def main():
    print("LCD 動畫測試開始")
    lcd.clear()
    load_chars()

    states = ["IDLE", "HAPPY", "LONELY", "CARING"]

    try:
        while True:
            for state in states:
                print(f"狀態：{state}")
                display_state(state, cycles=2)
                time.sleep(0.5)

    except KeyboardInterrupt:
        lcd.clear()
        print("結束")


if __name__ == "__main__":
    main()

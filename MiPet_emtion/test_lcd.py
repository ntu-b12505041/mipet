from RPLCD.i2c import CharLCD
import time

I2C_ADDR = 0x27
lcd = CharLCD('PCF8574', I2C_ADDR, port=1, cols=16, rows=2)

def draw(row1, row2):
    lcd.cursor_pos = (0, 0)
    lcd.write_string(row1)
    lcd.cursor_pos = (1, 0)
    lcd.write_string(row2)

EYE_ROW    = "    \x00     \x00     "
MOUTH_ROW  = "       \x01        "
LONELY_ROW = "    \x02  \x01  \x02     "


def anim_happy(duration=6):
    print("[LCD] HAPPY ^_^")
    OPEN_EYE = (0b00000, 0b01010, 0b11111, 0b00000, 0b00000, 0b00000, 0b00000, 0b00000)
    BLINK    = (0b00000, 0b00000, 0b11111, 0b00000, 0b00000, 0b00000, 0b00000, 0b00000)
    WINK     = (0b00000, 0b00000, 0b11100, 0b00000, 0b00000, 0b00000, 0b00000, 0b00000)
    SMILE    = (0b00000, 0b00000, 0b10001, 0b01110, 0b00000, 0b00000, 0b00000, 0b00000)

    lcd.create_char(0, OPEN_EYE)
    lcd.create_char(1, SMILE)
    lcd.create_char(2, WINK)
    lcd.clear()

    t        = time.time()
    blink_at = t + 2.0
    wink_at  = t + 4.5
    winked   = False
    while time.time() < t + duration:
        now = time.time()
        if not winked and now >= wink_at:
            draw("    \x00     \x02     ", MOUTH_ROW)
            time.sleep(0.4)
            winked = True
        elif now >= blink_at:
            lcd.create_char(0, BLINK)
            draw(EYE_ROW, MOUTH_ROW)
            time.sleep(0.15)
            lcd.create_char(0, OPEN_EYE)
            blink_at = now + 2.5
        else:
            draw(EYE_ROW, MOUTH_ROW)
        time.sleep(0.08)


def anim_lonely(duration=7):
    print("[LCD] LONELY T_T")
    SAD_EYE = (0b01010, 0b11111, 0b00000, 0b00000, 0b00000, 0b00000, 0b00000, 0b00000)
    FROWN   = (0b00000, 0b00000, 0b01110, 0b10001, 0b00000, 0b00000, 0b00000, 0b00000)
    TEARS   = [
        (0b00100, 0b00110, 0b00000, 0b00000, 0b00000, 0b00000, 0b00000, 0b00000),
        (0b00000, 0b00100, 0b00110, 0b00011, 0b00000, 0b00000, 0b00000, 0b00000),
        (0b00000, 0b00000, 0b00100, 0b00110, 0b00011, 0b00001, 0b00000, 0b00000),
        (0b00000, 0b00000, 0b00000, 0b00000, 0b00000, 0b00000, 0b00000, 0b00000),
    ]

    lcd.create_char(0, SAD_EYE)
    lcd.create_char(1, FROWN)
    lcd.create_char(2, TEARS[0])
    lcd.clear()

    t          = time.time()
    tear_frame = 0
    tear_next  = t + 1.5
    while time.time() < t + duration:
        now = time.time()
        if now >= tear_next:
            tear_frame = (tear_frame + 1) % len(TEARS)
            lcd.create_char(2, TEARS[tear_frame])
            tear_next = now + (2.0 if tear_frame == 0 else 0.4)
        draw(EYE_ROW, LONELY_ROW)
        time.sleep(0.08)


def anim_caring(duration=6):
    print("[LCD] CARING ><")
    INTENSE = (0b10001, 0b01010, 0b00100, 0b01010, 0b10001, 0b00000, 0b00000, 0b00000)
    SOFT    = (0b00000, 0b10001, 0b01010, 0b00100, 0b00000, 0b00000, 0b00000, 0b00000)
    SMILE   = (0b00000, 0b00000, 0b10001, 0b01110, 0b00000, 0b00000, 0b00000, 0b00000)

    lcd.create_char(0, INTENSE)
    lcd.create_char(1, SMILE)
    lcd.clear()

    t        = time.time()
    pulse_at = t + 0.9
    intense  = True
    while time.time() < t + duration:
        now = time.time()
        if now >= pulse_at:
            intense = not intense
            lcd.create_char(0, INTENSE if intense else SOFT)
            pulse_at = now + 0.9
        draw(EYE_ROW, MOUTH_ROW)
        time.sleep(0.08)


def anim_idle(duration=7):
    print("[LCD] IDLE -_-")
    OPEN_EYE = (0b00000, 0b00000, 0b11111, 0b00000, 0b00000, 0b00000, 0b00000, 0b00000)
    HALF_EYE = (0b00000, 0b00000, 0b01110, 0b00000, 0b00000, 0b00000, 0b00000, 0b00000)
    FLAT_MO  = (0b00000, 0b00000, 0b00000, 0b11111, 0b00000, 0b00000, 0b00000, 0b00000)
    YAWN_MO  = (0b00000, 0b01110, 0b11111, 0b01110, 0b00000, 0b00000, 0b00000, 0b00000)

    lcd.create_char(0, OPEN_EYE)
    lcd.create_char(1, FLAT_MO)
    lcd.clear()

    t        = time.time()
    blink_at = t + 3.5
    yawn_at  = t + 5.0
    yawned   = False
    while time.time() < t + duration:
        now = time.time()
        if not yawned and now >= yawn_at:
            lcd.create_char(0, HALF_EYE)
            lcd.create_char(1, YAWN_MO)
            draw(EYE_ROW, MOUTH_ROW)
            time.sleep(1.2)
            lcd.create_char(0, OPEN_EYE)
            lcd.create_char(1, FLAT_MO)
            yawned = True
        elif now >= blink_at:
            lcd.create_char(0, HALF_EYE)
            draw(EYE_ROW, MOUTH_ROW)
            time.sleep(0.2)
            lcd.create_char(0, OPEN_EYE)
            blink_at = now + 3.5
        else:
            draw(EYE_ROW, MOUTH_ROW)
        time.sleep(0.08)


print("LCD 動態表情測試開始")
lcd.clear()
lcd.cursor_pos = (0, 0)
lcd.write_string("  MiPet v1.0    ")
lcd.cursor_pos = (1, 0)
lcd.write_string("  Loading...    ")
time.sleep(1.5)

anim_happy(6)
anim_lonely(7)
anim_caring(6)
anim_idle(7)

lcd.clear()
lcd.cursor_pos = (0, 0)
lcd.write_string("  Test DONE!    ")
lcd.cursor_pos = (1, 0)
lcd.write_string("  All states OK ")
print("LCD 動態表情測試完成")

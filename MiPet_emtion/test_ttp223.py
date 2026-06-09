from gpiozero import Button, Device
from gpiozero.pins.lgpio import LGPIOFactory
import time

Device.pin_factory = LGPIOFactory()

TTP223_PIN = 25

print("TTP223 測試開始（GPIO 23）")
print("請觸碰感測器，Ctrl+C 結束\n")

ttp223 = Button(TTP223_PIN, pull_up=False)

while True:
    if ttp223.is_pressed:
        print("✅ 觸碰偵測到！")
        while ttp223.is_pressed:
            time.sleep(0.05)
        print("   放開")
    time.sleep(0.05)

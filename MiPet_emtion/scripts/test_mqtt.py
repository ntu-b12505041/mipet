"""
scripts/test_mqtt.py
模擬 Pi / ESP32 發送 MQTT 訊息，用於在沒有硬體時測試後端

用法：
  python3 scripts/test_mqtt.py                  # 互動選單
  python3 scripts/test_mqtt.py touched          # 直接發單一事件
  python3 scripts/test_mqtt.py vision owner     # 發視覺結果
  python3 scripts/test_mqtt.py vision stranger
"""

import sys
import json
import time
import paho.mqtt.client as mqtt

BROKER = "broker.emqx.io"
PORT   = 1883
PREFIX = "mimicpet/"

def publish(topic, payload: dict):
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.connect(BROKER, PORT, 60)
    client.loop_start()
    msg = json.dumps(payload)
    result = client.publish(PREFIX + topic, msg)
    result.wait_for_publish()
    client.loop_stop()
    client.disconnect()
    print(f"[送出] {PREFIX}{topic} → {msg}")

def send_event(event: str):
    publish("event", {"event": event})

def send_vision(result: str, person: str = "owner_1"):
    if result == "owner":
        publish("vision", {"result": "owner", "person": person})
    else:
        publish("vision", {"result": "stranger"})

EVENTS = [
    ("touched",       "被摸"),
    ("idle_too_long", "久沒互動"),
    ("fallen",        "跌倒"),
    ("arrived_home",  "到家"),
    ("left_home",     "外出"),
    ("sleeping",      "睡覺"),
    ("gps_lost",      "GPS 遺失"),
    ("high_stress",   "高壓力"),
]

def interactive():
    print("=" * 40)
    print("MimicPet MQTT 模擬器")
    print("=" * 40)
    print("\n--- mimicpet/event ---")
    for i, (evt, desc) in enumerate(EVENTS, 1):
        print(f"  {i}. {evt}（{desc}）")
    print("\n--- mimicpet/vision ---")
    print(f"  {len(EVENTS)+1}. vision: owner（辨識到主人）")
    print(f"  {len(EVENTS)+2}. vision: stranger（辨識到陌生人）")
    print("\n  0. 離開")
    print()

    while True:
        try:
            choice = input("選擇 > ").strip()
        except (KeyboardInterrupt, EOFError):
            break

        if choice == "0":
            break
        elif choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(EVENTS):
                send_event(EVENTS[idx][0])
            elif idx == len(EVENTS):
                send_vision("owner")
            elif idx == len(EVENTS) + 1:
                send_vision("stranger")
        else:
            print("無效選項")

if __name__ == "__main__":
    args = sys.argv[1:]

    if not args:
        interactive()
    elif args[0] == "vision":
        result = args[1] if len(args) > 1 else "owner"
        send_vision(result)
    else:
        send_event(args[0])

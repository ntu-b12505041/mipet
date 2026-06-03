import time
from pi_emotion import handle_event

print("=== 測試 IDLE（預設）===")
time.sleep(3)

print("=== 測試 HAPPY（觸碰兩次）===")
handle_event("touched")
handle_event("touched")
time.sleep(5)

print("=== 測試 LONELY（owner_stressed 後計時結束，再衰減）===")
handle_event("owner_stressed")
time.sleep(5)

print("=== 測試 CARING（owner_stressed 直接觸發）===")
handle_event("owner_stressed")
time.sleep(5)

print("=== 測試完成 ===")

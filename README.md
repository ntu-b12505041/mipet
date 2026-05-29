# MiPet Raspberry Pi Self-Driving Car

這個專案是依照 Notion 規格建立的第一版 MiPet 自駕車程式。目標是使用 Raspberry Pi、Camera、TB6612、兩顆 TT 減速馬達完成：

- 地面黑線或色帶循線
- 左右輪差速轉向
- 紅色告示牌或 ArUco marker 偵測停止
- 不使用 Arduino、不使用超音波
- 可先在一般電腦乾跑，再搬到 Raspberry Pi 接 GPIO

## 專案結構

```text
mipet_car/
├── main.py          # 主迴圈：相機、辨識、決策、馬達整合
├── camera.py        # OpenCV 相機讀取
├── vision_line.py   # 地面路線偵測
├── vision_sign.py   # 紅色告示牌 / ArUco 偵測
├── decision.py      # 狀態機與差速控制
├── motor.py         # TB6612 馬達控制
└── config.py        # GPIO 腳位與調校參數
```

## 建議接線

預設 GPIO 腳位集中在 `mipet_car/config.py`，接線不同時只要改那裡。

| TB6612 | Raspberry Pi 預設腳位 | 說明 |
| --- | --- | --- |
| AIN1 | GPIO 5 | 左馬達方向 |
| AIN2 | GPIO 6 | 左馬達方向 |
| PWMA | GPIO 12 | 左馬達 PWM |
| BIN1 | GPIO 20 | 右馬達方向 |
| BIN2 | GPIO 21 | 右馬達方向 |
| PWMB | GPIO 13 | 右馬達 PWM |
| STBY | GPIO 16 | TB6612 啟用 |
| VCC | 3.3V | 邏輯電源 |
| VM | 馬達電池正極 | 馬達電源 |
| GND | Pi GND + 電池負極 | 必須共地 |

重要：Raspberry Pi GND、TB6612 GND、馬達電池負極一定要共地。

## Cursor SSH 開發流程

到時候建議把這個資料夾放到 Raspberry Pi 上，再用 Cursor 的 Remote SSH 直接連進去編輯與執行。

1. 在 Raspberry Pi 啟用 SSH。
2. 在電腦確認可以連線：`ssh pi@raspberrypi.local`
3. 在 Cursor 安裝 Remote SSH 擴充功能。
4. 用 Cursor 連到 `pi@raspberrypi.local`。
5. 在 Cursor 裡開啟 Raspberry Pi 上的專案資料夾。
6. 先跑相機與馬達分開測試，再跑整合主程式。

如果 `raspberrypi.local` 找不到，可以改用 Raspberry Pi 的 IP，例如 `ssh pi@192.168.1.23`。

## 安裝

在 Raspberry Pi 上：

```bash
bash scripts/setup_pi.sh
```

這個腳本會建立 `.venv`，並用 Raspberry Pi OS 的系統套件安裝 OpenCV、NumPy、Flask、GPIO 控制套件與 Picamera2，比在樹莓派上用 pip 編譯 OpenCV 穩定。

如果想手動安裝：

```bash
sudo apt update
sudo apt install -y python3-venv python3-opencv python3-gpiozero python3-numpy python3-flask python3-picamera2
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
python -m unittest discover -s tests
```

## 本機測試

先跑單元測試：

```powershell
python -m unittest discover -s tests
```

乾跑馬達，不會輸出 GPIO：

```powershell
python scripts/test_motor.py --dry-run
```

測相機畫面：

```powershell
python scripts/test_camera.py --camera 0
```

測循線與告示牌偵測，但不開馬達：

```powershell
python -m mipet_car.main --dry-run --debug --camera 0
```

## Flask 網頁串流測試

不用 VNC。SSH 進 Raspberry Pi 後，在專案資料夾啟動 venv：

```bash
cd ~/mipet
source .venv/bin/activate
```

如果是 USB camera，先跑：

```bash
python scripts/stream_camera.py --host 0.0.0.0 --port 5000 --camera 0 --backend opencv
```

如果是 Raspberry Pi Camera Module，改跑：

```bash
python scripts/stream_camera.py --host 0.0.0.0 --port 5000 --backend picamera2
```

接著在 Windows 瀏覽器打開：

```text
http://172.20.10.2:5000
```

頁面會顯示相機串流、循線狀態、offset、左右輪速度建議值，以及是否偵測到告示牌。這個串流只做視覺測試，不會控制馬達。

停止串流時，在 SSH 終端機按 `Ctrl + C`。

## 食物偵測停止

食物偵測使用 TensorFlow Lite SSD MobileNet 類型的物件偵測模型。模型檔與 labels 放在 `models/`，例如：

```text
models/detect.tflite
models/labelmap.txt
```

下載官方 starter model：

```bash
python scripts/download_food_model.py
```

Raspberry Pi 需要 TFLite runtime。若 apt 找不到 `python3-tflite-runtime`，請在 venv 中用 pip 安裝：

```bash
source .venv/bin/activate
python -m pip install tflite-runtime || python -m pip install ai-edge-litert
```

啟動含食物偵測的串流測試：

```bash
cd ~/mipet
source .venv/bin/activate
python scripts/stream_camera.py \
  --host 0.0.0.0 \
  --port 5000 \
  --backend picamera2 \
  --sign-mode none \
  --food-model models/detect.tflite \
  --food-labels models/labelmap.txt \
  --food-classes banana,apple,orange,bottle,cup,bowl \
  --food-threshold 0.50 \
  --food-stop-seconds 5
```

偵測到目標食物時，狀態會變成 `FOOD_DETECTED`，左右輪速度會變成 `0.00 / 0.00`，並暫停 5 秒。若沒有偵測到食物，程式會繼續使用黑線 offset 做自由巡線。

## 與組員程式整合

建議組員把右半部主人互動程式放到 GitHub，同一個 repository 最好，分開 repository 也可以。最簡單流程：

```bash
git clone <組員的 repo URL>
```

把組員的主人偵測與互動模式整理成一個可呼叫的 Python 模組，例如：

```python
owner_result = owner_detector.detect(frame)
```

整合時優先序建議維持：

```text
主人互動 > 食物偵測停止 > 固定區域巡線
```

也就是先判斷是否看到主人；若看到主人，切到組員的互動模式。沒有主人時，再判斷是否看到食物；看到食物停 5 秒。都沒有時，才回到黑線巡線。

## cv2.imshow 遠端畫面測試

這個方法適合你的兩個終端機流程：一個終端機 SSH 到 Raspberry Pi 開相機串流，另一個 Windows 終端機用 `cv2.imshow()` 彈出視窗。

終端機 1，SSH 到 Raspberry Pi：

```bash
cd ~/mipet
source .venv/bin/activate
python scripts/stream_camera.py --host 0.0.0.0 --port 5000 --backend picamera2
```

如果你用的是 USB camera，改成：

```bash
python scripts/stream_camera.py --host 0.0.0.0 --port 5000 --camera 0 --backend opencv
```

終端機 2，在 Windows PowerShell，不要進 SSH：

```powershell
cd "C:\Users\yu891\OneDrive\桌面\mipet"
py -3 -m venv .venv-win
.\.venv-win\Scripts\Activate.ps1
pip install opencv-python numpy
python scripts\view_stream.py --url http://172.20.10.2:5000/stream.mjpg
```

這時 Windows 會跳出 OpenCV 視窗，顯示來自 Raspberry Pi 的真實影像與辨識狀態。按 `q` 關閉視窗。

產生 ArUco 停止告示牌圖片：

```powershell
python scripts/generate_aruco_marker.py --id 0 --output aruco_0.png
```

## Raspberry Pi 實車執行

確認車輪懸空後，先測馬達：

```bash
source .venv/bin/activate
python scripts/test_motor.py
```

確認相機能看到地面線：

```bash
source .venv/bin/activate
python scripts/test_camera.py --camera 0
```

低速整合測試：

```bash
source .venv/bin/activate
python -m mipet_car.main --camera 0 --base-speed 0.30 --max-speed 0.55 --kp 0.55
```

偵測到停止告示牌後，程式預設會鎖定停止狀態，避免告示牌短暫離開畫面後車子又繼續動。

## 調校重點

- 車子左右蛇行：降低 `--base-speed` 或 `--kp`
- 轉彎太慢：提高 `--kp` 或 `--max-speed`
- 找不到線：調整 `LineDetectionConfig.black_value_max`、相機角度、補光
- 太晚停：降低 `SignDetectionConfig.red_area_ratio_min` 或使用更大的 ArUco marker
- 背景紅色誤判：改用 ArUco marker，或把 `--sign-mode aruco`

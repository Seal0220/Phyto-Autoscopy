
# GOAL.md

# Phyto-Autoscopy

## CHLOROCULUS v0.1

### 植物多視角運動捕捉與旋轉控制系統

---

## 1. 專案名稱

### 1.1 計畫名稱

**Phyto-Autoscopy**

**綠色自視症**

`Phyto` 指向植物、植物性與植物身體；`Autoscopy` 原指觀看自身、從身體外部看見自己，亦帶有自體分身、體外視覺與感知錯位的意味。

在本專案中，Phyto-Autoscopy 並不是主張植物具有與人類相同的視覺，而是透過外部感測器、攝影機、旋轉機構與時間序列影像，為植物建立一套人工生成的外部觀看系統。

植物不再只是一個被人類凝視的靜物，而是透過多重視角、持續時間與身體運動，被重新組成一個能夠從外部觀看自身的影像主體。

「綠色自視症」不是對植物感知能力的生物學宣稱，而是描述一種由裝置介入後形成的異常觀看狀態：植物被置入多重視角構成的外部感知場中，其身體以影像、時間、角度與運動資料的形式反覆出現、分裂並重新組合。

---

### 1.2 裝置名稱

**CHLOROCULUS**

名稱由以下字根組成：

- `Chloro`：綠色、葉綠素、植物性的綠
- `Oculus`：眼睛、視覺器官、觀測孔

CHLOROCULUS 是 Phyto-Autoscopy 計畫中的實體捕捉裝置。

它由三組相機、一組旋轉機構、一組步進馬達、馬達控制器、電源系統與本機電腦控制介面構成。

CHLOROCULUS 可被理解為：

- 一個外接於植物的人工視覺器官
- 一個環繞植物運動的觀測眼
- 一個將植物身體轉譯為時間、角度與影像資料的捕捉裝置
- 一個讓植物從多個外部位置被重新組成的自視機器

---

### 1.3 名稱層級

```text
Phyto-Autoscopy
└─ CHLOROCULUS v0.1
   ├─ CHLOROCULUS CORE
   ├─ CHLOROCULUS ARM
   ├─ CHLOROCULUS EYE-TOP
   ├─ CHLOROCULUS EYE-SIDE
   └─ CHLOROCULUS EYE-ARM
```

名稱對應：

| 名稱                     | 對應內容                     |
| ------------------------ | ---------------------------- |
| `Phyto-Autoscopy`      | 整體研究、藝術命題與軟體專案 |
| `綠色自視症`           | Phyto-Autoscopy 的中文暫譯   |
| `CHLOROCULUS`          | 實體多視角植物捕捉裝置       |
| `CHLOROCULUS CORE`     | 電腦、控制器、電源與軟體系統 |
| `CHLOROCULUS ARM`      | 水平旋轉相機臂               |
| `CHLOROCULUS EYE-TOP`  | 正上方固定相機               |
| `CHLOROCULUS EYE-SIDE` | 固定側視相機                 |
| `CHLOROCULUS EYE-ARM`  | 旋轉臂末端相機               |

---

## 2. 專案目標

建立一套以 Python 為核心的植物多視角影像捕捉系統，整合三組 USB 相機、一組步進馬達與一組 PhidgetStepper Bipolar HC 控制器，並提供可由 Windows 電腦直接操作的本機 Web 控制介面。

系統主要用於長時間記錄植物的：

- 生長
- 擺動
- 攀爬
- 向性運動
- 莖尖旋轉
- 葉片位移
- 身體姿態變化
- 空間結構變化

系統取得以下三種主要視角：

1. 固定俯視影像
2. 固定側視影像
3. 旋轉側視影像

影像資料將供後續研究與處理使用，包括：

- 植物尖端運動追蹤
- 多視角影像比對
- 植物時間序列分析
- 三維運動軌跡重建
- 植物三維模型重建
- COLMAP
- Structure from Motion
- Multi-View Stereo
- NeRF
- 3D Gaussian Splatting
- 長時間植物行為分析
- 植物身體與視角關係研究
- 植物外部感知器官的藝術實驗

初始版本以穩定、可維護、可擴充與硬體安全為優先，不在第一階段加入 AI 辨識或即時三維重建。

---

## 3. 核心概念

Phyto-Autoscopy 並不只是「拍攝植物」。

它所建立的是一套以植物為中心的觀看場。

三顆相機分別形成：

- 上方觀看
- 固定側向觀看
- 環繞式移動觀看

其中旋轉相機不斷改變觀看位置，使植物不再被壓縮成單一視角的平面圖像，而是透過多個角度被反覆拆解與重組。

CHLOROCULUS 的旋轉不是為了展示裝置本身，而是將視角轉化為可控制的空間參數。

每張影像都必須與以下資訊綁定：

- 時間
- 相機角色
- 拍攝角度
- 馬達位置
- 實驗週期
- 植物個體
- Session
- 系統狀態

因此，CHLOROCULUS 所產生的不是單純照片集合，而是一組具有時間、空間與身體位置關係的植物視覺檔案。

「綠色自視症」描述的不是植物真正看見了自己，而是植物身體被放入一套外部視覺迴路後，開始以多重影像形態觀看、遭遇並複製自身的狀態。

---

## 4. 核心設計原則

### 4.1 單一 Python 系統

整個系統由 Python 啟動與管理，不另外建立：

- Node.js
- npm
- Vite
- React
- Vue
- Webpack
- 獨立前端專案

Python 系統負責：

- Web Server
- REST API
- WebSocket 或 Server-Sent Events
- HTML Template
- Tailwind CSS 靜態資源
- Vanilla JavaScript
- 相機控制
- 馬達控制
- 實驗排程
- 影像儲存
- Metadata 管理
- SQLite
- Logging
- Mock Hardware
- 測試

整套系統必須可透過單一 Python 啟動指令執行。

---

### 4.2 模組化

不同責任必須拆分為獨立模組，不得將所有功能集中於單一 Python 檔案。

主要模組分為：

- Web
- API
- Camera Hardware
- Motor Hardware
- Experiment Services
- Capture Services
- Rotation Services
- Storage
- Database
- Configuration
- Logging
- Mock Hardware
- Tests

每個模組只負責單一範圍，避免硬體控制、網頁介面、資料儲存與實驗排程彼此糾纏。

---

### 4.3 設定一律使用 JSON

本專案所有設定檔一律使用 JSON，不使用 YAML。

JSON 用於：

- 系統設定
- 相機設定
- 馬達設定
- Logging 設定
- Session 資訊
- 實驗設定
- Web API
- 系統狀態交換
- 校正資料索引
- 使用者介面設定
- 裝置角色設定

影像逐筆紀錄可使用 CSV，方便後續以 Python、R 或試算表分析。

---

### 4.4 本機優先

初始版本採本機運作。

系統預設：

- 不上傳雲端
- 不依賴外部伺服器
- 不依賴網路才能操作
- 影像儲存在本機磁碟
- Web 介面運行於 localhost 或區域網路
- Tailwind CSS 正式版本使用本機靜態檔案

---

### 4.5 硬體抽象化

相機與馬達控制必須透過介面抽象化。

Web 介面與實驗服務不可直接操作 OpenCV 或 Phidget API。

應由硬體層提供統一介面：

```text
CameraInterface
MotorControllerInterface
```

實體硬體與 Mock Hardware 必須實作相同介面。

---

## 5. 實體硬體

### 5.1 相機

相機型號：

`1.3M Low illumination USB Camera Module - CM1.3M30M12Q（FOV 110°）`

數量：

`3 組`

相機角色：

| 裝置名稱                 | 程式代號                | 安裝位置       | 用途                         |
| ------------------------ | ----------------------- | -------------- | ---------------------------- |
| `CHLOROCULUS EYE-TOP`  | `camera_top`          | 植物正上方固定 | 記錄俯視輪廓與平面運動       |
| `CHLOROCULUS EYE-SIDE` | `camera_fixed_side`   | 植物側邊固定   | 記錄植物高度、姿態與側向運動 |
| `CHLOROCULUS EYE-ARM`  | `camera_rotating_arm` | 旋轉臂末端     | 取得不同角度的環繞影像       |

所有相機透過 USB 連接 Windows 電腦，由 OpenCV 管理。

系統需支援：

- 相機掃描
- 相機角色指定
- 即時預覽
- 單張拍攝
- 三相機拍攝
- 相機重新連線
- 解析度設定
- FPS 設定
- JPEG 品質設定
- 曝光設定
- 白平衡設定
- 相機斷線偵測
- 相機錯誤重試
- USB 裝置重新對應
- 相機啟用與停用
- 相機狀態監測

---

### 5.2 步進馬達

馬達型號：

`NEMA-17 Bipolar 48mm Stepper Motor（0.9° Step Angle）`

主要規格：

- NEMA 17
- 雙極二相步進馬達
- 步距角 0.9°
- 每圈 400 個全步
- 軸徑 5 mm
- 馬達本體深度約 48 mm
- 額定相電流依實際商品規格設定
- 初始規劃最大值為 2.4A／相

用途：

- 控制 CHLOROCULUS ARM 水平旋轉
- 由原點向指定角度移動
- 於指定角度停止拍攝
- 完成拍攝後返回原點
- 不進行無限同方向旋轉
- 避免旋轉相機 USB 線纏繞

---

### 5.3 馬達控制器

控制器型號：

`PhidgetStepper Bipolar HC`

功能：

- USB 連接 Windows 電腦
- 由 Phidget22 Python API 控制
- Engage
- Disengage
- 設定 Current Limit
- 設定 Holding Current
- 設定速度
- 設定加速度
- 設定目標位置
- 查詢命令位置
- 控制正轉與反轉
- 停止馬達
- 回報控制器連線狀態
- 回報馬達控制狀態

此控制器不包含編碼器回授。

初始版本採用開迴路控制，依靠：

- 低速運動
- 平滑加減速
- 機構配重
- 軟體角度限制
- 人工確認原點
- 每次週期返回原點
- 移動逾時保護

未來可增加：

- 霍爾感測器
- 光電原點感測器
- 實體限位開關
- 編碼器回授
- 閉迴路馬達控制器

---

### 5.4 電源供應器

電源型號：

`MEAN WELL RS-100-24`

規格：

- 輸出電壓：24V DC
- 最大輸出電流：4.5A
- 額定功率：108W
- 輸入電壓：88 至 264VAC
- 短路保護
- 過負載保護
- 過電壓保護

接線架構：

```text
AC 市電
    ↓
MEAN WELL RS-100-24
    ↓ 24V DC
PhidgetStepper Bipolar HC
    ↓ 馬達四線
NEMA-17 Stepper Motor
```

USB 僅負責電腦與控制器之間的通訊，不負責馬達供電。

馬達不可直接連接 RS-100-24，必須經過 PhidgetStepper 控制器。

RS-100-24 接線原則：

```text
L  → AC 火線
N  → AC 中性線
FG → 保護接地

V+ → PhidgetStepper 電源正極
V- → PhidgetStepper 電源負極
```

市電端必須：

- 安裝端子護蓋
- 正確接地
- 於斷電狀態下接線
- 避免裸露導線
- 避免將 AC 與 USB、相機訊號線混放
- 使用適當線徑
- 必要時加裝保險絲
- 必要時加裝總電源開關
- 將電源固定於不可直接碰觸的位置

---

### 5.5 CHLOROCULUS ARM

CHLOROCULUS ARM 安裝於馬達下方，在水平面內旋轉。

基本結構：

```text
上方固定機構
    ↓
步進馬達本體
    ↓
5 mm 馬達軸
    ↓
夾緊式法蘭聯軸器
    ↓
旋轉臂連接結構
    ↓
CHLOROCULUS ARM
    ↓
CHLOROCULUS EYE-ARM
```

旋轉臂總重量可能接近 2 kg，因此不可單純將完整重量與側向彎矩交給 5 mm 馬達軸長期承受。

正式機構應包含：

- 獨立承重軸承或旋轉支撐
- 旋轉臂配重
- 重心接近旋轉中心
- 低速啟動
- 平滑加減速
- 防鬆螺帽
- 夾緊式法蘭聯軸器
- 相機線材固定
- 線材拉力釋放
- 防撞空間
- 機構停止位置標記
- 可拆卸相機支架
- 可調整相機俯仰角度
- 可調整旋轉半徑

馬達主要負責產生旋轉扭矩，機構支撐負責承受旋轉臂重量與側向力。

---

## 6. 旋轉邏輯

CHLOROCULUS ARM 不進行無限連續旋轉，而是在限定角度範圍內往復運動。

基本流程：

```text
原點 0°
    ↓
依序移動至指定拍攝角度
    ↓
等待機構穩定
    ↓
CHLOROCULUS EYE-ARM 拍照
    ↓
移動至下一個角度
    ↓
抵達最大角度
    ↓
反向返回原點
```

範例：

```text
0° → 15° → 30° → 45° → ... → 360° → 0°
```

也可設定較小範圍：

```text
0° → 180° → 0°
```

初始版本預設採用分段停拍，不在旋轉過程中持續錄影。

原因包括：

- 降低動態模糊
- 降低 Rolling Shutter 變形
- 減少馬達震動對影像的影響
- 讓影像與角度資料更容易對應
- 降低馬達與機構負載
- 提高多視角重建資料的一致性

---

## 7. 馬達安全規則

系統必須限制以下參數：

- 最小角度
- 最大角度
- 最大速度
- 最大加速度
- 最大 Current Limit
- 最大 Holding Current
- 馬達移動逾時
- 同時間只能執行一個馬達任務
- 實驗停止時禁止新的移動命令
- 系統關閉前停止馬達
- 異常時自動 Disengage
- 禁止在馬達移動期間重新設定原點
- 禁止超出軟體限位

初始建議設定：

```json
{
  "motor": {
    "name": "CHLOROCULUS_ARM_MOTOR",
    "controller": "phidget_stepper_bipolar_hc",
    "full_step_angle_deg": 0.9,
    "microstep_division": 16,
    "current_limit_amp": 1.5,
    "maximum_current_limit_amp": 2.4,
    "holding_current_amp": 0.3,
    "velocity_limit_deg_s": 3.0,
    "acceleration_deg_s2": 3.0,
    "minimum_angle_deg": 0.0,
    "maximum_angle_deg": 360.0,
    "movement_timeout_seconds": 180,
    "stabilization_delay_ms": 800,
    "return_to_origin_after_cycle": true,
    "disengage_after_cycle": false
  }
}
```

第一次測試時：

1. 先移除旋轉臂負載或降低負載。
2. Current Limit 從 1.5A 開始。
3. 速度從 3°/s 開始。
4. 加速度從 3°/s² 開始。
5. 確認旋轉方向。
6. 確認馬達線圈配對。
7. 確認旋轉臂不會碰撞周邊結構。
8. 確認停止按鈕正常。
9. 再逐步增加負載與速度。
10. Current Limit 不得超過馬達額定相電流。

---

## 8. 影像捕捉模式

### 8.1 即時預覽

Web 介面顯示三台相機的即時畫面。

為降低 USB 頻寬與 CPU 使用率，預覽可使用：

- 較低解析度
- 較低 FPS
- JPEG 串流
- 最新畫面緩衝區
- 畫面抽幀
- 預覽與正式拍照分離

正式拍照仍保存完整解析度影像。

---

### 8.2 單張拍攝

使用者可：

- 拍攝 CHLOROCULUS EYE-TOP
- 拍攝 CHLOROCULUS EYE-SIDE
- 拍攝 CHLOROCULUS EYE-ARM
- 同時觸發三台相機拍攝

每張影像必須包含：

- Session ID
- Cycle ID
- Camera ID
- Device Name
- Timestamp
- Angle
- Motor Position
- File Path
- Capture Status
- Error Message

---

### 8.3 定時拍攝

可設定：

- 拍攝間隔
- 實驗持續時間
- 開始時間
- 每個週期是否旋轉
- 旋轉角度範圍
- 角度間隔
- 每個角度的穩定等待時間
- 是否拍攝固定相機
- 是否拍攝旋轉相機
- 是否返回原點

設定範例：

```json
{
  "experiment": {
    "project_name": "Phyto-Autoscopy",
    "project_name_zh": "綠色自視症",
    "device_name": "CHLOROCULUS",
    "capture_interval_seconds": 60,
    "duration_minutes": 240,
    "capture_top": true,
    "capture_fixed_side": true,
    "capture_rotating_arm": true,
    "rotation_enabled": true,
    "rotation_start_deg": 0.0,
    "rotation_end_deg": 360.0,
    "rotation_step_deg": 15.0,
    "stabilization_delay_ms": 800,
    "return_to_origin": true
  }
}
```

---

### 8.4 分段旋轉拍攝

每一個旋轉週期：

1. 拍攝 CHLOROCULUS EYE-TOP。
2. 拍攝 CHLOROCULUS EYE-SIDE。
3. CHLOROCULUS ARM 移動到第一個角度。
4. 等待機構停止。
5. 等待額外穩定時間。
6. 拍攝 CHLOROCULUS EYE-ARM。
7. 記錄角度與時間戳。
8. 移動到下一個角度。
9. 重複直到完成全部角度。
10. 返回原點。
11. 完成該週期 Metadata 寫入。

---

### 8.5 旋轉錄影

可預留旋轉錄影功能，但不列為第一階段必要功能。

若未來啟用，需記錄：

- 錄影開始時間
- 錄影結束時間
- 馬達起始角度
- 馬達結束角度
- 馬達速度
- 每幀推估角度
- 實際 FPS

初始版本優先採用分段停拍。

---

## 9. 軟體技術

| 類別          | 技術                            |
| ------------- | ------------------------------- |
| Web 後端      | FastAPI                         |
| Web Server    | Uvicorn                         |
| HTML Template | Jinja2                          |
| 前端樣式      | Tailwind CSS                    |
| 前端腳本      | Vanilla JavaScript              |
| 即時狀態      | WebSocket 或 Server-Sent Events |
| 相機控制      | OpenCV                          |
| 馬達控制      | Phidget22 Python API            |
| 設定管理      | JSON                            |
| 資料驗證      | Pydantic                        |
| 資料庫        | SQLite                          |
| ORM           | SQLAlchemy                      |
| 影像儲存      | 本機檔案系統                    |
| Logging       | Python logging                  |
| 測試          | pytest                          |

---

## 10. Tailwind CSS 使用原則

前端不使用：

- Node.js
- npm
- Vite
- React
- Vue
- Webpack
- Tailwind CLI Runtime

Tailwind CSS 採以下方式：

1. 將預先編譯完成的 `tailwind.min.css` 放入 Python 專案。
2. FastAPI 直接提供此 CSS 靜態檔案。
3. 開發初期可暫時使用 Tailwind CDN。
4. 正式版本改用本機 CSS，避免依賴網路。

檔案位置：

```text
app/web/static/css/tailwind.min.css
```

整個系統透過單一 Python 指令啟動。

---

## 11. 專案檔案結構

```text
phyto-autoscopy/
│
├─ app/
│  ├─ __init__.py
│  ├─ main.py
│  ├─ lifespan.py
│  │
│  ├─ api/
│  │  ├─ __init__.py
│  │  ├─ camera_routes.py
│  │  ├─ motor_routes.py
│  │  ├─ capture_routes.py
│  │  ├─ experiment_routes.py
│  │  ├─ session_routes.py
│  │  ├─ settings_routes.py
│  │  └─ system_routes.py
│  │
│  ├─ core/
│  │  ├─ __init__.py
│  │  ├─ config.py
│  │  ├─ logging_config.py
│  │  ├─ exceptions.py
│  │  ├─ constants.py
│  │  ├─ state.py
│  │  └─ shutdown.py
│  │
│  ├─ hardware/
│  │  ├─ __init__.py
│  │  │
│  │  ├─ cameras/
│  │  │  ├─ __init__.py
│  │  │  ├─ camera_device.py
│  │  │  ├─ camera_manager.py
│  │  │  ├─ camera_registry.py
│  │  │  ├─ camera_identifier.py
│  │  │  ├─ frame_buffer.py
│  │  │  └─ camera_types.py
│  │  │
│  │  └─ motor/
│  │     ├─ __init__.py
│  │     ├─ motor_controller.py
│  │     ├─ phidget_stepper.py
│  │     ├─ motor_state.py
│  │     ├─ motor_profile.py
│  │     ├─ motor_safety.py
│  │     └─ motor_worker.py
│  │
│  ├─ services/
│  │  ├─ __init__.py
│  │  ├─ capture_service.py
│  │  ├─ rotation_service.py
│  │  ├─ experiment_service.py
│  │  ├─ preview_service.py
│  │  ├─ storage_service.py
│  │  ├─ metadata_service.py
│  │  ├─ session_service.py
│  │  └─ health_service.py
│  │
│  ├─ models/
│  │  ├─ __init__.py
│  │  ├─ camera_models.py
│  │  ├─ motor_models.py
│  │  ├─ capture_models.py
│  │  ├─ experiment_models.py
│  │  ├─ session_models.py
│  │  ├─ settings_models.py
│  │  └─ system_models.py
│  │
│  ├─ repositories/
│  │  ├─ __init__.py
│  │  ├─ session_repository.py
│  │  ├─ capture_repository.py
│  │  ├─ experiment_repository.py
│  │  └─ settings_repository.py
│  │
│  ├─ database/
│  │  ├─ __init__.py
│  │  ├─ connection.py
│  │  ├─ schema.py
│  │  └─ migrations/
│  │
│  └─ web/
│     ├─ __init__.py
│     ├─ page_routes.py
│     │
│     ├─ templates/
│     │  ├─ base.html
│     │  ├─ dashboard.html
│     │  ├─ cameras.html
│     │  ├─ motor.html
│     │  ├─ experiments.html
│     │  ├─ sessions.html
│     │  ├─ settings.html
│     │  └─ error.html
│     │
│     └─ static/
│        ├─ css/
│        │  └─ tailwind.min.css
│        ├─ js/
│        │  ├─ app.js
│        │  ├─ camera-preview.js
│        │  ├─ motor-control.js
│        │  ├─ experiment-control.js
│        │  ├─ settings.js
│        │  └─ websocket.js
│        └─ icons/
│
├─ config/
│  ├─ default.json
│  ├─ cameras.json
│  ├─ motor.json
│  ├─ experiments.json
│  └─ logging.json
│
├─ data/
│  ├─ captures/
│  ├─ calibration/
│  ├─ database/
│  ├─ logs/
│  └─ temp/
│
├─ scripts/
│  ├─ list_cameras.py
│  ├─ test_camera.py
│  ├─ test_motor.py
│  ├─ set_motor_origin.py
│  ├─ initialize_database.py
│  └─ validate_config.py
│
├─ tests/
│  ├─ unit/
│  │  ├─ test_camera_manager.py
│  │  ├─ test_motor_controller.py
│  │  ├─ test_rotation_service.py
│  │  ├─ test_capture_service.py
│  │  └─ test_storage_service.py
│  │
│  ├─ integration/
│  │  ├─ test_camera_api.py
│  │  ├─ test_motor_api.py
│  │  ├─ test_experiment_api.py
│  │  └─ test_capture_cycle.py
│  │
│  └─ mocks/
│     ├─ mock_camera.py
│     └─ mock_motor.py
│
├─ requirements.txt
├─ pyproject.toml
├─ run.py
├─ .env.example
├─ .gitignore
├─ README.md
└─ GOAL.md
```

---

## 12. 模組責任

### 12.1 `hardware/cameras`

只負責與實體相機溝通，包括：

- 開啟相機
- 關閉相機
- 設定解析度
- 設定 FPS
- 設定曝光
- 設定白平衡
- 讀取畫面
- 拍照
- 重新連線
- 回報相機狀態

不得在此模組中加入：

- Web 邏輯
- 實驗排程
- 資料庫操作
- 馬達控制
- Session 建立

---

### 12.2 `hardware/motor`

只負責與 PhidgetStepper 溝通，包括：

- 連接控制器
- 關閉控制器
- Engage
- Disengage
- 設定電流
- 設定 Holding Current
- 設定速度
- 設定加速度
- 移動至目標位置
- 停止
- 回報目前命令位置
- 回報連線狀態

不得在此模組中直接處理：

- 相機拍攝
- Web API
- 實驗資料夾
- Metadata
- Session 排程

---

### 12.3 `services/rotation_service.py`

負責 CHLOROCULUS ARM 的完整運動流程：

- 計算角度序列
- 控制正向移動
- 控制反向返回
- 等待馬達停止
- 加入穩定等待時間
- 觸發旋轉相機拍攝
- 防止超出軟體限位
- 處理移動逾時
- 處理緊急停止
- 回到原點

---

### 12.4 `services/capture_service.py`

負責：

- 三台相機同步拍攝
- 單台相機拍攝
- 產生檔名
- 寫入 Metadata
- 驗證影像
- 回報拍攝成功或失敗
- 避免多執行緒同時操作同一相機

---

### 12.5 `services/experiment_service.py`

負責：

- 建立實驗
- 實驗開始
- 實驗暫停
- 實驗繼續
- 實驗停止
- 定時拍攝
- 呼叫旋轉服務
- 維持實驗狀態
- 防止重複啟動
- 記錄實驗錯誤
- 控制 Session 生命週期

---

## 13. 相機識別與設定

三台相機型號相同，Windows 中的相機編號可能在重新插拔或重新開機後改變。

系統不得只依賴：

```text
camera 0
camera 1
camera 2
```

系統需提供相機指定流程：

1. 掃描所有可用相機。
2. 在 Web 介面顯示各相機即時預覽。
3. 使用者指定相機角色。
4. 儲存至 `config/cameras.json`。
5. 系統啟動時載入設定。
6. 若相機順序改變，允許重新對應。
7. 若可取得硬體識別資訊，優先使用裝置路徑或 USB ID。

設定範例：

```json
{
  "cameras": {
    "top": {
      "device_name": "CHLOROCULUS EYE-TOP",
      "device_index": 0,
      "width": 1280,
      "height": 960,
      "preview_fps": 5,
      "capture_fps": 10,
      "jpeg_quality": 95
    },
    "fixed_side": {
      "device_name": "CHLOROCULUS EYE-SIDE",
      "device_index": 1,
      "width": 1280,
      "height": 960,
      "preview_fps": 5,
      "capture_fps": 10,
      "jpeg_quality": 95
    },
    "rotating_arm": {
      "device_name": "CHLOROCULUS EYE-ARM",
      "device_index": 2,
      "width": 1280,
      "height": 960,
      "preview_fps": 5,
      "capture_fps": 10,
      "jpeg_quality": 95
    }
  }
}
```

---

## 14. 實驗資料結構

每次實驗建立獨立資料夾：

```text
data/captures/
└─ session_2026-07-10_001/
   ├─ session.json
   ├─ metadata.csv
   │
   ├─ top/
   │  ├─ 000001.jpg
   │  ├─ 000002.jpg
   │  └─ ...
   │
   ├─ fixed_side/
   │  ├─ 000001.jpg
   │  ├─ 000002.jpg
   │  └─ ...
   │
   └─ rotating_arm/
      ├─ cycle_000001/
      │  ├─ angle_000.0.jpg
      │  ├─ angle_015.0.jpg
      │  ├─ angle_030.0.jpg
      │  └─ ...
      └─ cycle_000002/
```

`session.json` 範例：

```json
{
  "project_name": "Phyto-Autoscopy",
  "project_name_zh": "綠色自視症",
  "device_name": "CHLOROCULUS",
  "device_version": "0.1",
  "session_id": "session_2026-07-10_001",
  "created_at": "2026-07-10T10:00:00+08:00",
  "status": "running",
  "experiment": {
    "capture_interval_seconds": 60,
    "duration_minutes": 240,
    "rotation_start_deg": 0.0,
    "rotation_end_deg": 360.0,
    "rotation_step_deg": 15.0
  },
  "hardware": {
    "camera_count": 3,
    "motor_controller": "PhidgetStepper Bipolar HC",
    "motor": "NEMA-17 Bipolar 48mm 0.9deg",
    "power_supply": "MEAN WELL RS-100-24"
  }
}
```

`metadata.csv` 欄位：

```csv
project_name,project_name_zh,device_name,session_id,cycle_id,camera_id,camera_name,timestamp,angle_deg,motor_position_deg,file_path,status,error_message
```

範例：

```csv
Phyto-Autoscopy,綠色自視症,CHLOROCULUS,session_001,1,top,CHLOROCULUS EYE-TOP,2026-07-10T10:00:00.100+08:00,,,top/000001.jpg,success,
Phyto-Autoscopy,綠色自視症,CHLOROCULUS,session_001,1,fixed_side,CHLOROCULUS EYE-SIDE,2026-07-10T10:00:00.150+08:00,,,fixed_side/000001.jpg,success,
Phyto-Autoscopy,綠色自視症,CHLOROCULUS,session_001,1,rotating_arm,CHLOROCULUS EYE-ARM,2026-07-10T10:00:02.000+08:00,0.0,0.0,rotating_arm/cycle_000001/angle_000.0.jpg,success,
Phyto-Autoscopy,綠色自視症,CHLOROCULUS,session_001,1,rotating_arm,CHLOROCULUS EYE-ARM,2026-07-10T10:00:05.000+08:00,15.0,15.0,rotating_arm/cycle_000001/angle_015.0.jpg,success,
```

---

## 15. Web 控制介面

Web 介面標題：

```text
Phyto-Autoscopy
綠色自視症
CHLOROCULUS Control Interface
```

---

### 15.1 Dashboard

顯示：

- CHLOROCULUS 系統狀態
- 三台相機連線狀態
- 馬達控制器連線狀態
- 馬達 Engage 狀態
- 目前旋轉臂命令位置
- 目前實驗狀態
- 已拍攝影像數量
- 磁碟剩餘容量
- 最近錯誤
- 緊急停止按鈕

---

### 15.2 Cameras

提供：

- 三台相機即時預覽
- 相機角色指定
- 解析度設定
- FPS 設定
- 單張拍照
- 全部相機拍照
- 相機重新連線
- 曝光設定
- 白平衡設定
- 相機啟用與停用
- 相機設定儲存

畫面名稱：

```text
CHLOROCULUS EYE-TOP
CHLOROCULUS EYE-SIDE
CHLOROCULUS EYE-ARM
```

---

### 15.3 Motor

提供：

- Engage
- Disengage
- 設為原點
- 返回原點
- 移動至指定角度
- 相對移動
- 正向移動
- 反向移動
- 設定速度
- 設定加速度
- 設定 Current Limit
- 設定 Holding Current
- 測試往返
- 停止
- 緊急停止

---

### 15.4 Experiments

提供：

- 建立實驗
- 設定拍攝間隔
- 設定實驗持續時間
- 設定旋轉角度範圍
- 設定角度間隔
- 設定穩定等待時間
- 選擇啟用的相機
- 開始
- 暫停
- 繼續
- 停止
- 返回原點

---

### 15.5 Sessions

提供：

- 查看歷史實驗
- 查看圖片數量
- 查看拍攝時間
- 查看錯誤紀錄
- 開啟實驗資料夾
- 下載 Metadata
- 查看 Session JSON
- 刪除測試資料

---

### 15.6 Settings

提供：

- 相機設定
- 馬達設定
- 儲存路徑
- 預覽 FPS
- JPEG 品質
- Logging 等級
- 系統啟動行為
- Mock Mode
- 設定匯入
- 設定匯出

---

## 16. API 初始規劃

### 16.1 相機 API

```text
GET  /api/cameras
GET  /api/cameras/{camera_id}/status
GET  /api/cameras/{camera_id}/stream
POST /api/cameras/{camera_id}/capture
POST /api/cameras/capture-all
POST /api/cameras/{camera_id}/reconnect
POST /api/cameras/{camera_id}/settings
```

---

### 16.2 馬達 API

```text
GET  /api/motor/status
POST /api/motor/engage
POST /api/motor/disengage
POST /api/motor/set-origin
POST /api/motor/move
POST /api/motor/move-relative
POST /api/motor/return-origin
POST /api/motor/stop
POST /api/motor/emergency-stop
POST /api/motor/test-cycle
POST /api/motor/settings
```

---

### 16.3 實驗 API

```text
GET  /api/experiments/status
POST /api/experiments/start
POST /api/experiments/pause
POST /api/experiments/resume
POST /api/experiments/stop
```

---

### 16.4 Session API

```text
GET    /api/sessions
GET    /api/sessions/{session_id}
DELETE /api/sessions/{session_id}
GET    /api/sessions/{session_id}/metadata
GET    /api/sessions/{session_id}/session-json
```

---

### 16.5 設定 API

```text
GET  /api/settings
GET  /api/settings/{group}
POST /api/settings/{group}
POST /api/settings/reload
POST /api/settings/reset
```

---

## 17. 系統啟動流程

```text
啟動 Python
    ↓
載入 JSON 設定
    ↓
驗證設定格式
    ↓
初始化 SQLite
    ↓
初始化 Logging
    ↓
掃描三台 USB 相機
    ↓
建立相機角色對應
    ↓
連接 PhidgetStepper
    ↓
馬達保持 Disengaged
    ↓
啟動 FastAPI
    ↓
開啟 CHLOROCULUS Web 控制介面
```

使用者確認機構安全後：

```text
確認 CHLOROCULUS ARM 位於原點
    ↓
按下「設為原點」
    ↓
設定 Current Limit
    ↓
Engage 馬達
    ↓
執行低速測試
```

---

## 18. 系統關閉流程

關閉程式時必須依序：

```text
停止實驗排程
    ↓
停止新的拍攝任務
    ↓
等待目前影像寫入完成
    ↓
停止 CHLOROCULUS ARM
    ↓
Disengage 馬達
    ↓
關閉 Phidget 連線
    ↓
釋放三台 OpenCV 相機
    ↓
關閉資料庫
    ↓
結束 Web Server
```

程式異常中止時，也應盡可能執行相同清理流程。

---

## 19. 執行緒與資源管理

每台相機必須由獨立擷取工作執行緒管理，避免 Web 預覽、拍照與實驗排程同時呼叫同一台相機造成衝突。

原則：

- 每台相機只允許一個底層 `VideoCapture`
- 最新畫面放入 Thread-Safe Frame Buffer
- Web 預覽從 Frame Buffer 取得影像
- 拍照服務複製最新完整影格
- 馬達只能由單一 Motor Worker 控制
- 同一時間只允許一個旋轉任務
- 所有硬體操作使用 Lock
- 緊急停止具有最高優先權
- Session 停止後不得新增拍攝任務
- 寫檔工作不得阻塞馬達安全控制

---

## 20. 錯誤處理

系統需處理：

- 相機未連接
- 相機突然斷線
- 相機畫面讀取失敗
- USB 頻寬不足
- Phidget 控制器未連接
- 馬達無法 Engage
- 馬達移動逾時
- 目標角度超過限制
- 寫入磁碟失敗
- 磁碟空間不足
- 實驗重複啟動
- WebSocket 中斷
- 設定 JSON 損壞
- 設定值超出安全範圍
- 程式非正常關閉
- CHLOROCULUS ARM 未返回原點
- 相機角色配置遺失

錯誤不得只顯示在終端機，也需：

- 寫入 Log
- 顯示於 Web 介面
- 記錄到 Session Metadata
- 必要時停止實驗
- 必要時停止馬達
- 必要時 Disengage 馬達

---

## 21. Mock 模式

系統必須支援未接實體設備時進行開發。

啟動方式：

```bash
python run.py --mock
```

Mock 模式提供：

- 三個模擬相機畫面
- 模擬馬達位置
- 模擬往返運動
- 模擬拍攝檔案
- 模擬錯誤
- 模擬相機斷線
- 完整 Web 介面測試

實體硬體模組與 Mock 模組必須實作相同介面，避免 Web 與服務層依賴特定硬體。

---

## 22. 初始依賴套件

```text
fastapi
uvicorn
jinja2
python-multipart
opencv-python
numpy
Phidget22
pydantic
pydantic-settings
sqlalchemy
aiofiles
pytest
httpx
```

JSON 使用 Python 標準函式庫處理，不額外加入 YAML 套件。

---

## 23. 第一階段交付目標

第一階段需完成：

- 可啟動 FastAPI Web 系統
- 可顯示 CHLOROCULUS Tailwind CSS 控制介面
- 不需 Node.js
- 可掃描並開啟三台 USB 相機
- 可指定三台相機角色
- 可顯示三台相機預覽
- 可分別拍攝三台相機
- 可同時觸發三台相機拍照
- 可透過 USB 連接 PhidgetStepper
- 可在 Web 介面 Engage 與 Disengage
- 可設定 Current Limit
- 可設定速度與加速度
- 可移動至指定角度
- 可從原點移動後返回原點
- 可建立實驗資料夾
- 可建立 Session JSON
- 可寫入 Metadata CSV
- 可於程式關閉時安全釋放硬體
- 可在 Mock 模式下完成所有介面測試

---

## 24. 第二階段交付目標

第二階段加入：

- 定時實驗排程
- 分段角度拍攝
- 多相機時間戳同步
- 實驗暫停與恢復
- 相機校正檔案管理
- Chessboard 校正工具
- 三相機內參管理
- 三相機外參管理
- WebSocket 即時狀態
- 磁碟容量警告
- 相機斷線自動重連
- 實驗資料匯出
- Session 瀏覽器
- 原點感測器支援

---

## 25. 未來擴充

後續可加入：

- 原點感測器
- 實體限位開關
- 編碼器回授
- 閉迴路馬達控制
- 植物尖端自動偵測
- 植物運動軌跡視覺化
- 三維重建處理流程
- COLMAP 自動任務
- 3D Gaussian Splatting
- NeRF
- 實驗遠端監看
- 自動備份
- 多植物 Session 管理
- 植物生長統計
- 燈光控制
- 溫濕度感測器
- 實驗異常通知
- 資料完整性驗證
- 自動校正流程
- CHLOROCULUS 裝置版本管理
- 多台 CHLOROCULUS 協同捕捉
- 植物身體數位分身
- 植物時間模型
- 植物姿態資料庫

---

## 26. 非目標

初始版本不處理：

- 馬達閉迴路控制
- 編碼器自動補償
- 無限同方向旋轉
- USB 滑環
- 雲端資料同步
- AI 自動辨識
- 即時三維重建
- 多使用者權限
- 手機 App
- Node.js 前端專案
- React
- Vue
- npm
- YAML

---

## 27. 驗收條件

系統達到以下條件即可視為初始版本完成：

1. Windows 電腦可透過單一 Python 指令啟動系統。
2. 不需啟動任何 Node.js 程序。
3. Web 介面能顯示三台相機畫面。
4. 三台相機可分別拍照並正確分類儲存。
5. PhidgetStepper 可由 Python 與 Web 介面控制。
6. CHLOROCULUS ARM 可從原點移動至設定角度，再安全返回原點。
7. 馬達不進行無限同方向旋轉。
8. 每張旋轉相機影像均具有時間戳與角度資料。
9. 系統關閉時，相機與馬達資源可正常釋放。
10. 單一硬體斷線不應導致整個 Web Server 崩潰。
11. 所有設定均集中於 JSON，不散落於程式碼。
12. 相機、馬達、實驗、儲存與 Web 介面均分離為獨立模組。
13. Mock 模式可在無實體設備時完整運作。
14. 緊急停止可立即阻止新的馬達移動命令。
15. 實驗資料可依 Session、相機與角度正確分類。
16. 系統介面與資料中使用 `Phyto-Autoscopy` 作為專案名稱。
17. 系統介面與資料中使用 `綠色自視症` 作為中文暫譯。
18. 系統介面與硬體識別中使用 `CHLOROCULUS` 作為裝置名稱。

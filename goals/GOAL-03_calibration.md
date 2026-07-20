# GOAL-03 — Unified Camera Calibration

# Phyto-Autoscopy

### 統一相機校正頁面、唯一內參與多組外參校正檔

---

## 1. 目標

建立一套獨立、統一、可直接操作實體硬體的相機校正系統。

校正功能不得繼續附屬於「分析」頁面，也不得依照「雙鏡頭校正」、「三鏡頭校正」或相機數量拆分成不同流程。

前端主導覽新增與「分析」同層級的獨立頁面：

```text
校正
```

建議路由：

```text
/calibration
```

校正頁面必須在單一頁面中直接完成：

- 相機即時預覽
- 相機選擇
- 相機重新連線
- 校正板即時偵測
- 內參影像擷取
- 內參計算
- 內參品質驗證
- 外參影像同步擷取
- 固定相機外參計算
- 旋臂相機外參計算
- 旋臂高度與位置資料輸入
- 馬達角度控制
- 世界座標設定
- 校正品質檢查
- 外參校正檔儲存
- 外參校正檔切換
- 外參校正檔啟用
- 校正結果匯出

校正流程以 OpenCV、ChArUco、PnP、幾何擬合與非線性最佳化為核心。

COLMAP 不屬於此校正階段，不得作為校正頁面的執行依賴。COLMAP 僅在後續模型建立、姿態精修與重建流程中使用。

---

## 2. 頁面與導覽層級

主導覽應包含與目前系統一致的主要頁面，並新增：

```text
分析
校正
```

「校正」必須與「分析」位於相同導覽層級。

校正不得存在於：

- 分析頁面的子區塊
- 分析頁面的折疊面板
- 分析頁面的設定區
- 分析頁面的彈出視窗
- 分析頁面的子路由
- 紀錄頁面的附屬功能
- 一般系統設定頁面

建議 App Router 入口：

```text
frontend/src/app/calibration/page.js
```

建議功能模組：

```text
frontend/src/features/Calibration/
```

---

## 3. 移除分析頁面的既有校正

必須從目前「分析」功能中完整移除所有校正相關介面、狀態與程式責任。

移除內容包括：

- 雙鏡頭校正區塊
- 三鏡頭校正區塊
- 依鏡頭數量分類的校正模式
- 棋盤格設定表單
- 重複出現的校正板參數
- 手動輸入 `4×4` 外參矩陣的欄位
- 手動輸入旋轉矩陣或平移向量的欄位
- 分析頁面中的校正狀態
- 分析頁面中的校正 API 呼叫
- 分析頁面中的校正資料讀寫
- 以分析工作流程為前提的校正資料模型
- 任何將模型分析與裝置校正耦合的邏輯

分析頁面只負責：

- 已有資料集的選擇
- 模型建立
- 三維重建
- 模型檢視
- 植物資料分析
- 表型或運動資料處理
- 後續 COLMAP、3DGS、NeRF 或 MVS 流程

分析頁面可以讀取已啟用的校正資料，但不得建立、修改或刪除校正資料。

---

## 4. 校正系統的統一模型

校正系統不得再區分：

```text
雙鏡頭校正
三鏡頭校正
```

校正系統只處理：

```text
一組參與校正的相機集合
```

目前正式相機識別碼為：

```text
top
side
rotating
```

繁體中文名稱為：

```text
top       俯視角
side      側視角
rotating  旋臂視角
```

校正演算法必須能接受任意一至多台相機。

目前系統使用三台相機，但資料模型不得將相機數量硬編碼為二或三。

相機之間的關係應以觀測圖表示：

```text
Camera Observation Graph
```

只要參與外參校正的相機能透過共同觀測形成連通關係，系統即可將它們統一至同一座標系。

例如：

```text
top ↔ rotating
side ↔ rotating
```

即使 `top` 與 `side` 無法同時看到同一個平面校正板，只要兩者都能與 `rotating` 建立有效關係，外參仍可統一求解。

---

## 5. 校正層級

校正資料必須分成以下四個層級：

```text
Intrinsics
Rig Extrinsics
Motion Model
World Alignment
```

### 5.1 Intrinsics

描述每顆相機自身的成像特性：

- 焦距 `fx`
- 焦距 `fy`
- 主點 `cx`
- 主點 `cy`
- 鏡頭畸變係數
- 相機模型
- 影像解析度
- 校正板資訊
- 重投影誤差
- 校正時間
- 使用影像數量
- 品質評估

### 5.2 Rig Extrinsics

描述固定相機與裝置座標之間的剛性關係：

- 俯視相機相對裝置座標的姿態
- 側視相機相對裝置座標的姿態
- 旋臂基座相對裝置座標的姿態
- 各相機相對其他相機的姿態

### 5.3 Motion Model

描述旋臂相機隨馬達角度與高度產生的姿態：

- 旋轉軸位置
- 旋轉軸方向
- 馬達零點偏移
- 旋臂相機相對安裝座的姿態
- 旋臂半徑
- 旋臂高度
- 升降軸方向
- 高度基準
- 馬達角度與相機姿態的轉換模型

### 5.4 World Alignment

描述整套裝置相對世界座標或植物拍攝區域的關係：

- 世界原點
- 世界 X 軸方向
- 世界 Y 軸方向
- 世界 Z 軸方向
- 植物中心位置
- 平台高度
- 單位
- 公制尺度

---

## 6. 內參資料規則

每一顆實體相機只能有一組目前有效的內參。

內參以 `camera_id` 作為唯一鍵：

```text
top
side
rotating
```

每顆相機不得建立多個可切換的內參 profile。

系統中的正式內參資料關係為：

```text
一顆相機
→ 一組唯一內參
```

重新執行內參校正並確認套用後，新結果取代舊結果。

舊內參可以保留於：

- 稽核紀錄
- 校正歷史紀錄
- 備份檔案

舊內參不得繼續作為可選擇的有效 profile 出現在操作介面。

### 6.1 內參唯一性

後端資料庫或檔案索引必須保證：

```text
UNIQUE(camera_id)
```

內參 API 不得允許同一 `camera_id` 同時存在兩組 active intrinsics。

### 6.2 內參有效條件

內參只適用於校正時對應的：

- 實體相機
- 鏡頭
- 焦距
- 對焦位置
- 影像解析度
- 影像裁切方式
- 影像縮放方式
- 相機模型

若以下任一條件改變，系統應將內參標示為可能失效：

- 更換鏡頭
- 調整鏡頭焦距
- 重新對焦
- 更換相機模組
- 改變正式拍攝解析度
- 改變裁切區域
- 改變影像比例
- 鏡頭鬆動
- 感光元件與鏡頭之間的機械關係改變

移動相機位置、旋轉相機方向或改變旋臂高度，不會使內參失效。

---

## 7. 外參資料規則

外參允許保存多組校正檔。

每一組外參校正檔代表一種完整的裝置幾何配置，例如：

```text
旋臂高度 300 mm
旋臂高度 450 mm
小型植物配置
高型植物配置
實驗室平台 A
實驗室平台 B
```

外參校正檔必須包含：

- 校正檔 ID
- 校正檔名稱
- 建立時間
- 更新時間
- 是否啟用
- 參與相機
- 相機位置
- 相機高度
- 相機姿態
- 旋臂高度
- 旋臂半徑
- 旋轉軸
- 馬達零點偏移
- 世界座標設定
- 校正板規格
- 誤差指標
- 品質狀態
- 備註

系統同一時間只能有一組 active 外參校正檔。

### 7.1 外參校正檔狀態

每組外參校正檔可具有：

```text
draft
validating
valid
invalid
active
archived
```

狀態意義：

- `draft`：尚未完成
- `validating`：正在計算或驗證
- `valid`：已通過品質檢查
- `invalid`：計算失敗或未達品質門檻
- `active`：目前拍攝系統使用
- `archived`：保留但不再使用

只有 `valid` 校正檔可以被設為 `active`。

設為新的 active 外參校正檔時，原 active 校正檔回到 `valid`。

---

## 8. 校正頁面設計

校正頁面採用單層頁面設計。

不得使用多層巢狀頁面、深層設定導覽或將內參與外參拆至不同路由。

頁面可使用區塊、卡片或頁內切換，但所有功能必須保留在同一個 `/calibration` 頁面中。

建議頁面結構：

```text
校正
├─ 校正狀態總覽
├─ 相機即時預覽與硬體控制
├─ 校正板設定
├─ 內參校正
├─ 外參校正
├─ 外參校正檔
└─ 品質與輸出
```

---

## 9. 校正狀態總覽

頁面頂部顯示：

- 三顆相機連線狀態
- 每顆相機內參是否存在
- 每顆相機內參是否有效
- 目前 active 外參校正檔
- active 外參校正檔品質
- 目前旋臂高度
- 目前馬達角度
- 校正板偵測狀態
- 最近一次校正時間
- 最近錯誤

狀態顯示範例：

```text
俯視角內參：有效
側視角內參：有效
旋臂視角內參：尚未校正
目前外參：高型植物配置
外參品質：通過
旋臂高度：450 mm
馬達角度：90°
```

---

## 10. 相機即時預覽與控制

校正頁面必須能直接開啟所有參與校正的相機。

不得要求使用者離開校正頁面到控制頁面操作相機。

每顆相機預覽必須提供：

- 即時影像
- 相機名稱
- 相機連線狀態
- 相機啟用狀態
- FPS
- 重新連線
- 單張擷取
- 全螢幕預覽
- 校正板角點覆蓋
- 偵測到的 marker 數量
- 偵測到的 ChArUco corner 數量
- 當前影像是否符合擷取條件
- 畫面清晰度提示
- 曝光過高或過低提示

校正頁面應重用現有相機串流與 camera manager。

不得為校正另外建立第二套相機硬體連線。

校正頁面與一般 ImagePreview 必須共享：

- CameraManager
- CameraWorker
- FrameBuffer
- CameraStatus
- reconnect 邏輯
- 裝置索引
- 相機啟用設定

同一顆相機不得被兩套獨立 worker 同時開啟。

---

## 11. 馬達與旋臂控制

外參校正區必須提供旋臂馬達控制。

操作內容包括：

- 顯示目前角度
- 移動至指定角度
- 移動至建議校正角度
- 返回原點
- 停止
- 緊急停止
- 設定或確認零點
- 顯示旋臂高度
- 輸入旋臂高度
- 儲存高度資料

校正頁面不得複製另一套馬達狀態。

所有控制仍使用既有：

- MotorController
- MotorWorker
- MotorSafety
- WebSocket command
- 排程鎖定
- 緊急停止機制

排程執行期間不得開始校正。

校正進行期間不得開始一般拍攝排程。

系統必須建立校正操作鎖：

```text
CalibrationLock
```

校正鎖啟用時：

- 禁止排程開始
- 禁止一般旋轉拍攝
- 禁止其他頁面改變相機設定
- 禁止其他頁面移動馬達
- 仍允許緊急停止
- 仍允許中止校正

---

## 12. 校正板

預設使用：

```text
ChArUco Board
```

系統可以保留一般 Chessboard 支援，但正式預設與推薦流程使用 ChArUco。

校正板設定包含：

- board type
- squares X
- squares Y
- square length
- marker length
- ArUco dictionary
- 單位
- 校正板 ID
- 校正板名稱

長度單位統一使用：

```text
millimeter
```

UI 顯示：

```text
mm
```

### 12.1 校正板資料

校正板設定可儲存為共用 board profile。

board profile 與內參或外參校正結果分離。

同一塊校正板可以重複用於：

- 俯視角內參
- 側視角內參
- 旋臂視角內參
- 多相機外參
- 世界座標對齊
- 快速外參重定位

### 12.2 校正板位置

內參校正時，校正板位置不固定。

外參校正時，同一組同步影像中的校正板不得移動。

世界座標設定時，校正板必須放置於已知、固定且可重複定位的位置。

---

## 13. 內參校正流程

內參校正以單一相機為單位執行。

使用者流程：

```text
選擇相機
→ 選擇校正板
→ 開啟即時預覽
→ 從不同位置與角度擷取校正板
→ 系統即時分析覆蓋率
→ 達到最低資料品質
→ 執行內參計算
→ 顯示結果
→ 驗證去畸變影像
→ 確認取代目前內參
```

### 13.1 內參影像擷取

校正影像應涵蓋：

- 畫面中央
- 左上
- 右上
- 左下
- 右下
- 畫面左側
- 畫面右側
- 畫面上側
- 畫面下側
- 不同距離
- 不同俯仰角
- 不同水平旋轉角
- 不同板面傾斜角

系統不得只以影像數量判斷資料是否足夠。

系統應分析：

- 校正板中心分布
- 角點覆蓋範圍
- 校正板尺度分布
- 俯仰角分布
- 偏航角分布
- 邊緣覆蓋程度
- 重複姿態比例
- 影像清晰度
- 角點品質

### 13.2 自動擷取

內參校正應支援：

```text
手動擷取
自動擷取
```

自動擷取模式只有在目前校正板姿態與既有樣本具有足夠差異時才保存影像。

不得因相機靜止而持續保存大量相同影像。

自動擷取需具備：

- 姿態差異判斷
- 最小時間間隔
- 模糊排除
- 角點數量門檻
- 覆蓋率判斷
- 重複樣本排除

### 13.3 相機模型

後端至少支援：

```text
opencv
opencv_rational
opencv_fisheye
```

系統可根據鏡頭規格與校正結果比較候選模型。

自動模型選擇不得只比較訓練資料的平均重投影誤差，也需檢查：

- 邊緣殘差
- 參數穩定性
- 去畸變後直線表現
- 留出影像誤差
- 過度擬合風險

使用者可在進階設定中手動指定模型。

### 13.4 內參輸出

每顆相機唯一內參至少包含：

```json
{
  "camera_id": "top",
  "resolution": {
    "width": 1280,
    "height": 960
  },
  "camera_model": "opencv",
  "camera_matrix": [
    [0.0, 0.0, 0.0],
    [0.0, 0.0, 0.0],
    [0.0, 0.0, 1.0]
  ],
  "distortion_coefficients": [],
  "reprojection_error_px": 0.0,
  "validation_error_px": 0.0,
  "sample_count": 0,
  "board_profile_id": "",
  "created_at": "",
  "updated_at": "",
  "status": "valid"
}
```

---

## 14. 外參校正流程

外參校正使用已完成的相機內參。

未完成內參校正的相機不得參與正式外參求解。

外參流程：

```text
建立外參校正檔
→ 輸入裝置配置與相機高度
→ 選擇參與相機
→ 選擇世界座標基準
→ 開啟相機即時預覽
→ 擷取共同觀測
→ 控制旋臂移動至不同角度
→ 擷取旋臂相機姿態
→ 求解相機關係
→ 求解旋轉軸與零點
→ 全域最佳化
→ 品質驗證
→ 儲存外參校正檔
→ 設為 active
```

### 14.1 固定相機

固定相機包含：

```text
top
side
```

每顆固定相機需保存：

- 相機高度
- 相機位置
- 相機朝向
- 相對 rig 的 transformation
- 相對 world 的 transformation
- 安裝備註
- 是否曾移動

### 14.2 旋臂相機

旋臂相機包含：

- 旋臂高度
- 旋臂半徑
- 相機安裝偏移
- 相機安裝旋轉
- 旋轉軸位置
- 旋轉軸方向
- 馬達零點偏移
- 可用角度範圍
- 校正時使用的角度
- 每個角度的觀測姿態
- 模型擬合殘差

旋臂相機姿態應由以下概念模型產生：

```text
T_world_from_camera(angle, height)
=
T_world_from_arm_base
× T_height(height)
× R_axis(angle + zero_offset)
× T_mount_from_camera
```

正式實作可採用等價的座標定義，但不得將每個角度保存為互不相關的手動矩陣。

### 14.3 建議旋臂角度

外參校正頁面應自動產生建議角度，例如：

```text
0°
45°
90°
135°
180°
225°
270°
315°
```

實際角度依馬達安全範圍與裝置幾何決定。

系統應顯示：

- 已完成角度
- 尚未完成角度
- 每個角度的校正板可見性
- 每個角度的有效相機
- 每個角度的擷取品質

---

## 15. 相機位置與高度資料

外參校正檔必須保存每顆相機的安裝位置資訊。

每顆相機至少包含：

```json
{
  "camera_id": "top",
  "position_label": "",
  "height_mm": 0.0,
  "offset_x_mm": 0.0,
  "offset_y_mm": 0.0,
  "offset_z_mm": 0.0,
  "mount_description": "",
  "is_movable": false
}
```

旋臂相機需額外包含：

```json
{
  "arm_height_mm": 0.0,
  "arm_radius_mm": 0.0,
  "motor_zero_offset_deg": 0.0,
  "rotation_axis_origin_mm": [0.0, 0.0, 0.0],
  "rotation_axis_direction": [0.0, 0.0, 1.0]
}
```

相機位置與高度資料用於：

- 協助選擇正確外參校正檔
- 判斷裝置配置是否改變
- 提供校正初始值
- 顯示操作提示
- 產生後續相機 pose
- 追蹤硬體重新安裝
- 對應植物高度範圍

位置與高度資料不得取代影像校正結果。

手動量測值屬於先驗與描述資料，正式外參仍由校正影像求解。

---

## 16. 世界座標

世界座標預設規則：

```text
原點：植物平台中心
XY 平面：植物承載平台
Z 軸：垂直向上
單位：毫米
```

世界座標設定應支援：

- 校正板固定定位座
- 已知尺寸定位標記
- 平台中心
- 平台平面
- 自訂原點偏移

UI 不得要求使用者手動輸入完整 `4×4` transformation matrix。

進階檢視可以顯示：

- transformation matrix
- rotation matrix
- translation vector
- quaternion
- Euler angles

所有矩陣欄位皆為唯讀。

---

## 17. 外參校正檔管理

校正頁面必須直接顯示外參校正檔列表。

每筆顯示：

- 名稱
- 狀態
- 建立時間
- 最後更新時間
- 旋臂高度
- 參與相機
- 平均重投影誤差
- 旋轉軸擬合誤差
- 是否 active

支援操作：

- 建立
- 重新命名
- 複製
- 繼續未完成校正
- 驗證
- 設為 active
- 匯出
- 封存
- 刪除

active 校正檔不得直接刪除。

刪除 active 校正檔前必須先啟用另一組有效校正檔。

---

## 18. 快速外參重定位

除完整外參校正外，校正頁面應支援：

```text
快速外參重定位
```

適用情況：

- 旋臂高度改變
- 相機支架輕微調整
- 裝置搬移
- 馬達零點重新設定
- 固定相機被重新安裝
- 需要驗證目前外參是否仍有效

快速重定位使用現有 active 外參作為初始值，只更新受影響部分。

使用者需選擇變動項目：

```text
旋臂高度改變
旋臂相機重新安裝
俯視相機移動
側視相機移動
整套裝置搬移
馬達零點改變
```

系統根據變動項目決定需重新求解的參數。

快速重定位不得默默覆寫 active 外參。

完成後應建立一組新的外參校正檔，讓使用者比較並確認啟用。

---

## 19. 品質驗證

### 19.1 內參品質

至少計算：

- 平均重投影誤差
- 中位數重投影誤差
- 最大重投影誤差
- 每張影像誤差
- 畫面區域覆蓋率
- 邊緣覆蓋率
- 姿態多樣性
- 留出影像驗證誤差
- 去畸變視覺預覽

品質狀態：

```text
excellent
acceptable
warning
failed
```

品質門檻需由後端集中設定，不得散落在前端 JSX。

### 19.2 外參品質

至少計算：

- 多相機重投影誤差
- 相機間姿態一致性
- 旋轉軸擬合誤差
- 馬達角度殘差
- 旋臂軌跡圓度
- 世界尺度誤差
- 校正板姿態一致性
- 有效共同觀測數量
- 相機觀測圖連通性
- 各相機有效影像數量

### 19.3 驗證視圖

外參完成後提供：

- 校正板座標軸疊圖
- 去畸變影像
- 各相機座標軸
- 旋轉臂相機軌跡
- 世界原點
- 旋轉軸
- 相機視錐
- 重投影點與觀測點差異

---

## 20. 儲存結構

校正資料儲存在：

```text
data/calibration/
```

建議結構：

```text
data/calibration/
├─ boards/
│  └─ default_charuco.json
├─ intrinsics/
│  ├─ top.json
│  ├─ side.json
│  └─ rotating.json
├─ extrinsics/
│  ├─ calibration_20260720_001/
│  │  ├─ profile.json
│  │  ├─ observations.json
│  │  ├─ quality.json
│  │  └─ captures/
│  └─ calibration_20260720_002/
│     ├─ profile.json
│     ├─ observations.json
│     ├─ quality.json
│     └─ captures/
└─ index.json
```

內參正式檔名固定：

```text
top.json
side.json
rotating.json
```

同一相機不得產生：

```text
top_01.json
top_02.json
top_final.json
```

外參則以獨立 profile 目錄保存。

---

## 21. 資料庫

若校正索引保存於 SQLite，建議資料表：

```text
camera_intrinsics
calibration_boards
extrinsic_profiles
extrinsic_profile_cameras
calibration_observations
calibration_runs
```

### 21.1 camera_intrinsics

必要欄位：

```text
camera_id
camera_model
width
height
camera_matrix_json
distortion_json
reprojection_error
validation_error
board_profile_id
sample_count
status
created_at
updated_at
```

`camera_id` 必須唯一。

### 21.2 extrinsic_profiles

必要欄位：

```text
profile_id
name
status
is_active
world_definition_json
motion_model_json
quality_json
notes
created_at
updated_at
```

### 21.3 extrinsic_profile_cameras

必要欄位：

```text
profile_id
camera_id
height_mm
position_json
transform_json
mount_description
```

---

## 22. 後端架構

建議新增：

```text
backend/app/api/calibration_routes.py

backend/app/models/calibration_models.py

backend/app/repositories/calibration_repository.py

backend/app/services/calibration_service.py
backend/app/services/intrinsic_calibration_service.py
backend/app/services/extrinsic_calibration_service.py
backend/app/services/calibration_capture_service.py
backend/app/services/calibration_validation_service.py

backend/app/calibration/
├─ board_detection.py
├─ camera_models.py
├─ intrinsic_solver.py
├─ extrinsic_solver.py
├─ observation_graph.py
├─ rotation_axis_solver.py
├─ world_alignment.py
└─ quality_metrics.py
```

責任必須分離。

API route 不得直接呼叫 OpenCV 求解。

CameraManager 不得加入校正演算法。

MotorController 不得加入外參計算。

CalibrationService 負責協調流程，實際數學求解由 calibration 模組完成。

---

## 23. API

建議 API：

```text
GET    /api/calibration/status
GET    /api/calibration/boards
POST   /api/calibration/boards

GET    /api/calibration/intrinsics
GET    /api/calibration/intrinsics/{camera_id}
POST   /api/calibration/intrinsics/{camera_id}/runs
POST   /api/calibration/intrinsics/{camera_id}/capture
POST   /api/calibration/intrinsics/{camera_id}/solve
POST   /api/calibration/intrinsics/{camera_id}/apply
DELETE /api/calibration/intrinsics/{camera_id}/runs/{run_id}

GET    /api/calibration/extrinsics
POST   /api/calibration/extrinsics
GET    /api/calibration/extrinsics/{profile_id}
PATCH  /api/calibration/extrinsics/{profile_id}
DELETE /api/calibration/extrinsics/{profile_id}

POST   /api/calibration/extrinsics/{profile_id}/capture
POST   /api/calibration/extrinsics/{profile_id}/solve
POST   /api/calibration/extrinsics/{profile_id}/validate
POST   /api/calibration/extrinsics/{profile_id}/activate
POST   /api/calibration/extrinsics/{profile_id}/archive

POST   /api/calibration/lock
DELETE /api/calibration/lock
```

所有 API 維持既有：

- BFF authentication
- operator identity
- role authorization
- audit logging
- input validation
- rate limiting
- same-origin frontend proxy

瀏覽器不得直接連接 FastAPI 硬體 API。

---

## 24. 即時狀態

校正過程中的即時狀態透過既有 WebSocket 傳送。

建議事件：

```text
calibration.status
calibration.board_detected
calibration.sample_added
calibration.sample_rejected
calibration.solve_started
calibration.solve_progress
calibration.solve_completed
calibration.solve_failed
calibration.profile_activated
```

WebSocket snapshot 可新增：

```json
{
  "calibration": {
    "locked": false,
    "mode": null,
    "run_id": null,
    "profile_id": null,
    "status": "idle",
    "progress": 0,
    "message": null
  }
}
```

不得透過高頻 WebSocket 傳送完整相機影像。

相機影像仍使用現有 MJPEG stream。

---

## 25. 前端架構

建議新增：

```text
frontend/src/app/calibration/page.js

frontend/src/features/Calibration/
├─ Calibration.js
├─ calibrationConfig.js
├─ components/
│  ├─ CalibrationHeader.js
│  ├─ CalibrationStatus.js
│  ├─ CalibrationCameraGrid.js
│  ├─ CalibrationCameraFeed.js
│  ├─ CalibrationBoardSettings.js
│  ├─ IntrinsicCalibration.js
│  ├─ IntrinsicCaptureProgress.js
│  ├─ IntrinsicResult.js
│  ├─ ExtrinsicCalibration.js
│  ├─ ExtrinsicProfileList.js
│  ├─ ExtrinsicProfileEditor.js
│  ├─ CalibrationMotorControls.js
│  ├─ CalibrationQuality.js
│  └─ CalibrationVisualization.js
├─ hooks/
│  ├─ useCalibration.js
│  ├─ useIntrinsicCalibration.js
│  ├─ useExtrinsicCalibration.js
│  └─ useCalibrationProfiles.js
└─ lib/
   ├─ calibrationUtils.js
   └─ calibrationValidation.js
```

校正頁面的相機顯示應重用現有共用 UI 元件與相機串流規則。

不得直接複製整份 ImagePreview feature。

可抽出共用元件，例如：

```text
CameraStreamViewport
CameraStatusBadge
CameraReconnectAction
CameraFullscreenDialog
```

---

## 26. 操作體驗

校正頁面應讓使用者打開後立即理解目前狀態。

不得先顯示大量矩陣、演算法選項或空白數值輸入。

主要操作順序：

```text
確認相機
→ 確認校正板
→ 選擇內參或外參
→ 依即時提示擷取
→ 自動計算
→ 查看品質
→ 確認套用
```

矩陣與完整數學參數只出現在：

```text
進階資料
```

進階資料預設折疊。

內參與外參區塊可以在同一頁面中分區顯示，但不得要求進入第二層頁面。

---

## 27. 錯誤處理

必須處理：

- 相機未連線
- 相機未啟用
- 內參不存在
- 校正板未偵測
- 角點不足
- 校正板過小
- 校正板過度模糊
- 影像過曝
- 樣本姿態重複
- 相機觀測圖不連通
- 旋臂移動失敗
- 馬達角度逾時
- 校正期間排程啟動
- 儲存空間不足
- 求解未收斂
- 重投影誤差過高
- 旋轉軸擬合失敗
- active profile 刪除衝突
- 解析度與既有內參不符

錯誤訊息應清楚指出：

- 哪一顆相機
- 哪一個步驟
- 發生原因
- 可採取的操作

不得只顯示：

```text
Calibration failed
```

---

## 28. 測試

### 28.1 後端單元測試

至少包含：

- 每顆相機只能有一組 active intrinsics
- 重新套用內參會取代舊值
- 不同解析度內參不可誤用
- 外參 profile 可以建立多組
- 同時只能有一組 active 外參
- invalid profile 不可啟用
- active profile 不可直接刪除
- 觀測圖連通性判斷
- 旋轉軸擬合
- 世界座標轉換
- 高度資料驗證
- 校正鎖
- 排程與校正互斥
- 校正取消後硬體狀態復原

### 28.2 後端整合測試

至少包含：

- 內參完整流程
- 外參完整流程
- 相機重新連線
- 馬達移動與擷取
- 校正失敗恢復
- profile 啟用
- 權限驗證
- BFF proxy
- audit log

### 28.3 前端測試

至少包含：

- 校正頁面導覽
- 即時相機預覽
- 內參擷取狀態
- 自動擷取拒絕重複樣本
- 外參 profile 建立
- profile 切換
- active profile 顯示
- 排程執行時禁止校正
- 校正期間禁止離開時的確認
- 錯誤訊息
- 響應式排版
- 鍵盤操作與無障礙標籤

---

## 29. 安全與硬體規則

校正頁面所有硬體操作必須遵守目前專案安全規則。

必須保留：

- 馬達軟體限位
- 速度限制
- 加速度限制
- 電流限制
- 移動逾時
- 停止
- 緊急停止
- 排程鎖
- 單一硬體控制來源
- 操作稽核

校正頁面不得提供跳過安全檢查的馬達指令。

校正演算法失敗不得影響馬達停止與相機關閉。

離開校正頁面時：

- 停止自動擷取
- 取消未完成求解
- 釋放校正鎖
- 保留已儲存樣本
- 不自動移動馬達
- 不自動刪除 draft profile

---

## 30. 與後續模型建立的關係

校正系統輸出的資料需可供後續流程讀取：

- COLMAP
- PyCOLMAP
- Nerfstudio
- 3D Gaussian Splatting
- NeRF
- MVS
- Open3D
- 自訂植物分析流程

GOAL-03 不執行：

- COLMAP feature extraction
- COLMAP matching
- SfM reconstruction
- MVS reconstruction
- NeRF training
- 3DGS training
- 植物模型分析

GOAL-03 只負責提供：

- 去畸變所需內參
- 相機初始姿態
- 旋臂角度對應姿態
- 世界座標
- 公制尺度
- 校正品質資訊

後續模型建立應由獨立目標處理，例如：

```text
GOAL-04_reconstruction.md
```

---

## 31. 完成條件

GOAL-03 完成時，系統必須符合以下條件：

1. 分析頁面不再包含任何校正介面。
2. 主導覽新增與分析同層級的「校正」頁面。
3. `/calibration` 可直接開啟。
4. 校正頁面可顯示三顆相機即時影像。
5. 校正頁面可直接重新連線相機。
6. 校正頁面可直接控制旋臂角度。
7. 校正頁面可直接輸入與保存旋臂高度。
8. 每顆相機只能有一組目前有效內參。
9. 三顆相同型號相機仍分別保存自己的內參。
10. 內參校正可在單一相機上獨立完成。
11. 內參校正可自動判斷樣本覆蓋率與姿態差異。
12. 內參校正結果可顯示去畸變預覽。
13. 外參校正不再區分雙鏡頭與三鏡頭。
14. 外參校正可選擇任意參與相機集合。
15. 外參校正可保存多組 profile。
16. 同時只能有一組 active 外參 profile。
17. 外參 profile 保存各相機位置與高度資料。
18. 外參 profile 保存旋轉軸與馬達零點偏移。
19. 所有矩陣由系統計算，不要求使用者手動輸入。
20. 校正期間與一般排程互斥。
21. 所有硬體操作通過既有安全層。
22. 所有校正變更寫入 audit log。
23. 校正資料儲存在 `data/calibration/`。
24. 校正結果可供後續重建流程讀取。
25. 校正頁面不直接執行 COLMAP 或模型重建。

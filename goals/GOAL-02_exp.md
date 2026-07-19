
# GOAL-02.md

# Phyto-Autoscopy

## CHLOROCULUS Analysis v0.2

### 植物尖端追蹤與雙鏡頭三維運動重建系統

---

## 1. 階段定位

Phyto-Autoscopy 第一階段已完成 CHLOROCULUS 的影像捕捉與硬體控制系統。

既有系統包含：

- Next.js App Router 前端
- React
- Tailwind CSS v4
- Next.js BFF
- FastAPI 硬體後端
- 三組相機控制
- CHLOROCULUS ARM 馬達控制
- 即時影像預覽
- 單次與排程擷取
- Capture Session
- 本機影像儲存
- SQLite
- WebSocket 即時狀態
- 使用者驗證與角色權限
- 稽核紀錄
- Mock Hardware
- Windows 啟動流程

GOAL-02 將在現有系統上加入「分析」區域。

本階段的第一個目標不是提出新的植物追蹤方法，而是優先重現以下論文所提出的技術流程：

> Ruiz-Melero, D. R., Ponkshe, A., Calvo, P., & García-Mateos, G.
> The Development of a Stereo Vision System to Study the Nutation Movement of Climbing Plants.
> Sensors, 2024, 24, 747.

在論文方法尚未成功實作、驗證並建立可比較的結果之前，不加入其他追蹤器、深度學習模型、3D Gaussian Splatting、行為分類或意識判定。

---

## 2. 頂層頁面分類

系統介面分為三個頂層區域：

```text
[ 捕捉 ] [ 分析 ] [ 模型 ]
```

### 2.1 捕捉

既有的 CHLOROCULUS 控制頁面歸入：

```text
/capture
```

包含：

- 相機即時預覽
- 影像擷取
- 馬達控制
- 分段旋轉
- 擷取排程
- 系統狀態
- 擷取紀錄
- 硬體設定

既有功能不得因頁面分類調整而退化。

---

### 2.2 分析

本階段新增：

```text
/analysis
```

包含：

- 可分析 Session
- Analysis Run
- 相機校正
- 雙鏡頭影格配對
- 植物尖端自動偵測
- 人工修正
- 三維位置重建
- 重投影誤差
- 三維軌跡
- CSV 與 JSON 匯出

---

### 2.3 模型

目前只保留入口：

```text
/models
```

本階段不實作模型訓練或 3DGS。

頁面顯示：

```text
模型模組尚未啟用
```

---

## 3. GOAL-02 核心目標

使用 CHLOROCULUS 的固定頂視相機與固定側視相機，建立一套遵照論文方法的雙鏡頭植物尖端追蹤系統。

系統需要完成：

1. 頂視與側視影像配對
2. 頂視相機個別校正
3. 側視相機個別校正
4. 雙鏡頭相機校正
5. 鏡頭畸變校正
6. Gaussian Mixture 背景分割
7. 頂視植物尖端候選點偵測
8. 頂視尖端時序選擇
9. 側視植物輪廓偵測
10. Epipolar Line 篩選
11. Minimum Path 尖端估計
12. 側視尖端時序選擇
13. 缺失影格線性插值
14. 人工位置修正
15. 雙鏡頭三角化
16. 三維尖端座標輸出
17. 重投影誤差計算
18. 三維植物運動軌跡顯示
19. 分析結果匯出
20. 偵測類型統計

---

## 4. 方法重現原則

### 4.1 論文方法優先

第一版分析方法固定為：

```text
top_side
```

其技術內容必須對應論文方法，不自行更換為其他追蹤方式。

第一版不加入：

- Kalman Filter
- Particle Filter
- Optical Flow
- 深度學習關鍵點模型
- 語意分割模型
- Transformer
- 物件偵測器
- 自動行為分類
- 植物意圖推論

---

### 4.2 原始資料唯讀

分析系統不得覆寫或修改：

```text
data/captures/
```

所有分析輸出寫入：

```text
data/analysis/
```

所有校正輸出寫入：

```text
data/calibration/
```

---

### 4.3 分析可重現

每次分析建立獨立的：

```text
Analysis Run
```

每個 Analysis Run 必須保存：

- Analysis ID
- Capture Session ID
- Calibration ID
- 方法名稱
- 方法版本
- Git Commit
- 分析參數
- 建立時間
- 操作者
- 輸入影格清單
- 自動偵測結果
- 人工修正結果
- 最終二維位置
- 三維位置
- 重投影誤差
- 輸出檔案
- 執行狀態
- 錯誤紀錄

---

### 4.4 自動結果與人工結果分離

系統需分別保存：

```text
automatic_detection
manual_correction
resolved_detection
```

人工修正不得覆寫原始自動結果。

每一個最終位置必須能追溯其來源。

---

## 5. 分析使用的相機

第一版只使用：

```text
CHLOROCULUS EYE-TOP
CHLOROCULUS EYE-SIDE
```

兩台固定相機形成頂視與側視 Stereo Pair。

建議實體位置維持約：

```text
90°
```

的觀看方向差異。

第一版不使用：

```text
CHLOROCULUS EYE-ARM
```

旋轉相機保留給後續：

- 多視角重建
- COLMAP
- 3D Gaussian Splatting
- NeRF
- 全株模型
- 模型預覽

---

## 6. 第一版追蹤目標

第一版只追蹤：

```text
植物主要生長尖端
Plant Tip
```

第一版不追蹤：

- 多個分枝尖端
- 莖節
- 所有葉片
- 卷鬚
- 根部
- 完整植物輪廓的三維位置
- 完整植物骨架
- 植物表面

---

## 7. 論文技術流程

整體流程固定為：

```text
Capture Session
    ↓
頂視與側視影像配對
    ↓
個別相機校正
    ↓
雙鏡頭相機校正
    ↓
頂視背景分割
    ↓
頂視尖端候選偵測
    ↓
頂視尖端時序選擇
    ↓
由頂視尖端計算側視 Epipolar Line
    ↓
側視背景分割
    ↓
側視輪廓篩選
    ↓
Minimum Path 尖端候選偵測
    ↓
側視尖端時序選擇
    ↓
缺失位置線性插值
    ↓
人工檢查與修正
    ↓
雙鏡頭三角化
    ↓
三維位置估計
    ↓
重投影誤差計算
    ↓
三維軌跡與結果匯出
```

---

## 8. 可分析 Session 條件

Session 至少需要：

- 頂視影像
- 固定側視影像
- 相機角色資訊
- 相機解析度
- 拍攝時間
- Cycle ID 或可對應的 Timestamp
- Session Metadata
- 有效的 Calibration Profile

若缺少必要資料，系統應標記：

```text
not_ready
```

並顯示無法分析的原因。

---

## 9. 影格配對

### 9.1 配對來源

目前 CHLOROCULUS 由同一系統控制相機，因此優先使用：

1. `cycle_id`
2. 同一 capture group
3. 最接近的 Timestamp

論文中的兩台相機各自使用內部時鐘，可能產生影格偏移，因此原方法會透過光暗週期判斷 Frame Offset。

為保留論文方法的相容性，系統仍需提供：

```text
manual_frame_offset
```

供使用者在時間同步錯誤時調整。

---

### 9.2 配對資料

每組影格配對保存：

```text
pair_id
cycle_id
top_frame_id
side_frame_id
top_timestamp
side_timestamp
timestamp_delta_ms
frame_offset
pair_status
```

狀態：

```text
paired
top_missing
side_missing
outside_tolerance
manually_aligned
```

---

### 9.3 配對設定

```json
{
  "synchronization": {
    "primary_key": "cycle_id",
    "timestamp_tolerance_ms": 1000,
    "manual_frame_offset": 0,
    "keep_unpaired_frames": true
  }
}
```

無法配對的影格不得默默刪除。

---

## 10. 相機校正

論文的校正分為兩個階段：

1. 分別進行頂視與側視相機的個別校正
2. 進行雙鏡頭相機校正

---

## 11. 個別相機校正

### 11.1 論文基準

論文使用：

```text
10 × 7 Chessboard Pattern
實體尺寸：59.4 × 84.1 cm
```

進行個別相機校正。

棋盤覆蓋影像中的大部分範圍，以估計：

- 相機內參
- 主點
- 焦距
- 徑向畸變
- 切向畸變
- 重投影誤差

Phyto-Autoscopy 第一版應優先依照此配置建立基準校正。

若實際裝置空間無法使用完全相同尺寸，可使用其他已知尺寸棋盤，但必須：

- 保持格點尺寸精確
- 在設定中記錄實際尺寸
- 覆蓋主要影像區域
- 保存與論文配置的差異

---

### 11.2 OpenCV 方法

使用：

```python
cv2.findChessboardCorners
cv2.cornerSubPix
cv2.calibrateCamera
cv2.projectPoints
```

輸出：

```text
camera_matrix
distortion_coefficients
rotation_vectors
translation_vectors
mean_reprojection_error
reprojection_error_per_image
```

---

### 11.3 鏡頭畸變

必須估計並保存：

```text
k1
k2
k3
p1
p2
```

其中：

- `k1`、`k2`、`k3` 為徑向畸變係數
- `p1`、`p2` 為切向畸變係數

分析影像應先進行畸變校正，再進行植物尖端偵測。

---

## 12. 雙鏡頭相機校正

### 12.1 論文基準

論文的雙鏡頭校正使用：

```text
42.0 × 59.4 cm
```

的校正物件，且必須同時被頂視與側視相機看到。

應從多組不同位置與姿態的校正影像估計：

```text
R
t
E
F
P_top
P_side
```

其中：

- `R`：相機之間的旋轉矩陣
- `t`：相機之間的平移向量
- `E`：Essential Matrix
- `F`：Fundamental Matrix
- `P_top`：頂視相機投影矩陣
- `P_side`：側視相機投影矩陣

---

### 12.2 OpenCV 方法

使用：

```python
cv2.stereoCalibrate
cv2.stereoRectify
cv2.computeCorrespondEpilines
cv2.projectPoints
```

必要時可使用：

```python
cv2.solvePnP
```

求取校正物件相對相機的姿態。

---

### 12.3 Calibration Profile

每一組校正結果保存為：

```text
Calibration Profile
```

至少包含：

```text
calibration_id
created_at
top_camera_identifier
side_camera_identifier
image_width
image_height
chessboard_pattern
square_size
top_camera_matrix
top_distortion_coefficients
side_camera_matrix
side_distortion_coefficients
rotation_matrix
translation_vector
essential_matrix
fundamental_matrix
top_projection_matrix
side_projection_matrix
top_mean_reprojection_error
side_mean_reprojection_error
stereo_mean_reprojection_error
valid
notes
```

---

### 12.4 校正品質

校正頁面應顯示：

- 使用的校正影像數
- 成功偵測角點的影像數
- 每張影像的角點
- 每張影像的重投影誤差
- 頂視平均重投影誤差
- 側視平均重投影誤差
- 雙鏡頭平均重投影誤差
- 校正點空間覆蓋

論文結果指出，高重投影誤差容易出現在缺少校正點覆蓋的區域。

因此校正物件必須盡可能覆蓋：

```text
植物尖端預期移動的完整三維空間
```

不能只在視野中央拍攝棋盤。

---

### 12.5 校正失效條件

以下變更發生後，Calibration Profile 應標記為可能失效：

- 頂視相機位置改變
- 側視相機位置改變
- 相機角度改變
- 鏡頭焦距改變
- 鏡頭重新安裝
- 相機解析度改變
- 相機硬體更換
- 支架重新組裝
- 相機角色交換

舊校正不得自動刪除，但系統需提示重新校正。

---

## 13. Gaussian Mixture 背景分割

論文使用每個像素由多個 Gaussian Distribution 組成的背景模型。

第一版使用 OpenCV：

```python
cv2.createBackgroundSubtractorMOG2
```

不得在第一版改用深度學習分割模型。

---

### 13.1 基本流程

```text
載入影像
    ↓
鏡頭畸變校正
    ↓
套用 ROI
    ↓
更新 Gaussian Mixture 背景模型
    ↓
產生前景遮罩
    ↓
取得植物輪廓
    ↓
依面積門檻排除雜訊
```

---

### 13.2 輪廓清理

可使用論文流程需要的傳統影像處理：

```python
cv2.morphologyEx
cv2.erode
cv2.dilate
cv2.findContours
```

可調參數包括：

```text
opening_kernel_size
closing_kernel_size
erosion_kernel_size
minimum_contour_area
```

這些操作只能用於清理背景分割結果，不得改變方法核心。

---

### 13.3 背景初始化

分析開始時需先使用一定數量的影格建立背景模型。

初始化期間的影格狀態標記為：

```text
background_initialization
```

在背景尚未穩定前，不輸出正式植物尖端結果。

---

## 14. 光照變化處理

論文中，光照切換會造成背景模型短暫失效。

論文方法透過植物輪廓面積突然超過門檻來判定光照變化。

需要保留的參數：

```text
lighting_change_area
lighting_change_est_time
```

基本流程：

```text
計算當前輪廓面積
    ↓
面積是否超過 lighting_change_area
    ↓
是
    ↓
標記光照改變
    ↓
重設 Gaussian Mixture 背景模型
    ↓
等待 lighting_change_est_time
    ↓
恢復植物尖端偵測
```

在等待期間，不重複判定光照變化。

相關影格標記為：

```text
lighting_transition
```

第一版不使用 Histogram、曝光值或神經網路取代論文的面積判斷方式。

---

## 15. 頂視植物尖端偵測

### 15.1 處理流程

```text
頂視影像
    ↓
畸變校正
    ↓
使用者設定 ROI
    ↓
MOG2 背景分割
    ↓
輪廓清理
    ↓
排除低於面積門檻的輪廓
    ↓
產生尖端候選點
    ↓
選擇最可能的尖端位置
```

---

### 15.2 頂視 ROI

使用者需要能在分析設定中指定：

```text
region_of_interest
```

ROI 用於：

- 排除裝置邊緣
- 排除花盆外無關區域
- 限制植物可能出現的範圍
- 降低背景分割雜訊

ROI 必須保存於 Analysis Run 的參數中。

---

### 15.3 候選點選擇

論文的候選點選擇規則固定為：

1. 若只有一個候選點，直接選取。
2. 若有多個候選點，選擇距離上一個已選尖端最近的候選點。
3. 若沒有候選點，將該影格暫時標記為缺失。
4. 缺失區段在後續使用線性插值處理。

第一版不加入：

- 速度預測
- 方向預測
- Kalman Filter
- Optical Flow
- 機率追蹤器
- 深度學習評分

---

### 15.4 頂視輸出

每一影格保存：

```text
frame_id
timestamp
candidate_count
candidate_points
selected_x_px
selected_y_px
detection_type
valid
```

---

## 16. 側視植物尖端偵測

### 16.1 處理流程

```text
側視影像
    ↓
畸變校正
    ↓
MOG2 背景分割
    ↓
取得側視植物輪廓
    ↓
由頂視尖端計算 Epipolar Line
    ↓
選擇接近 Epipolar Line 的輪廓
    ↓
在輪廓中執行 Minimum Path Algorithm
    ↓
取得側視尖端候選點
    ↓
使用時序規則選擇最終位置
```

---

### 16.2 Epipolar Line

使用：

```text
Fundamental Matrix
+
頂視尖端二維位置
```

計算該點在側視影像中的 Epipolar Line。

建議使用：

```python
cv2.computeCorrespondEpilines
```

側視候選輪廓必須位於或接近該 Epipolar Line。

這個約束用於排除：

- 無關植物碎片
- 背景前景誤判
- 不可能與頂視尖端對應的輪廓

---

### 16.3 Minimum Path Algorithm

論文在選出接近 Epipolar Line 的輪廓後，使用 Minimum Path Algorithm 尋找可能的植物尖端。

實作需包含：

1. 取得植物基部或路徑起點。
2. 將植物輪廓或骨架轉換為圖結構。
3. 計算基部至候選位置的路徑。
4. 依論文方法選出潛在尖端位置。
5. 保存路徑與候選結果供檢查。

第一版不得以「輪廓最高點」或「最遠像素」直接取代 Minimum Path Algorithm。

---

### 16.4 側視重疊問題

論文指出，當植物尖端與莖重疊時，Minimum Path 可能把其他莖段誤判為尖端。

因此這些情況必須進入人工修正流程。

系統應保存：

- 原始側視影像
- 前景遮罩
- 選定輪廓
- Epipolar Line
- Minimum Path
- 最終候選點

---

## 17. 時序候選選擇

頂視與側視使用相同時序規則：

```text
只有一個候選點
    → Automatic

多個候選點
    → 選擇距離上一個位置最近者
    → Estimated

沒有候選點
    → Missing
    → 後續進行 Linear Interpolation
```

時序處理按照影格順序執行。

第一個有效影格若存在多個候選點，需由使用者人工指定初始尖端位置。

---

## 18. 線性插值

論文使用前後有效位置，對沒有候選點的影格進行 Linear Interpolation。

第一版只實作：

```text
Linear Interpolation
```

不加入：

- Cubic Spline
- Kalman Smoothing
- Gaussian Process
- Learned Interpolation

---

### 18.1 插值條件

只有在缺失區段前後皆有有效位置時才可插值。

不得跨越：

- 相機斷線
- Capture Session 中斷
- 長時間資料缺口
- 無法配對的雙鏡頭影格
- 人工標記的無效區段
- 光照切換尚未穩定的區段

插值結果標記為：

```text
Interpolated
```

---

## 19. 偵測類型

第一版沿用論文的四種類型：

### Automatic

```text
演算法只找到一個尖端候選位置。
```

### Estimated

```text
演算法找到多個候選位置，
並依與上一影格尖端的距離選出最可能位置。
```

### Interpolated

```text
演算法沒有找到候選位置，
以缺失區段前後的有效位置進行線性插值。
```

### Manual

```text
使用者人工修改或指定的位置。
```

內部可另外使用：

```text
Missing
Invalid
```

但論文比較統計應以四個主要類型為核心。

---

## 20. 人工修正工具

論文建立 Plant Tracker 供使用者修正錯誤偵測。

Phyto-Autoscopy 需在 Web 中實作相同核心能力。

---

### 20.1 Review 頁面

路由：

```text
/analysis/[analysisId]/review
```

畫面同時顯示：

- 頂視影像
- 側視影像
- 目前影格編號
- Timestamp
- 自動尖端位置
- 最終尖端位置
- 頂視候選點
- 側視候選點
- 頂視植物輪廓
- 側視植物輪廓
- Epipolar Line
- Minimum Path
- 偵測類型
- 前一影格
- 下一影格

---

### 20.2 基本操作

使用者可：

- 點擊頂視影像重新指定尖端
- 點擊側視影像重新指定尖端
- 拖曳既有位置
- 清除人工修正
- 將影格標記為無效
- 切換上一影格
- 切換下一影格
- 播放影像序列
- 暫停播放
- 跳到指定影格
- 儲存修改

第一版不需要：

- 多人協作標註
- 信心分數排序
- 主動學習
- 複雜 Review Queue
- AI 自動建議

---

### 20.3 快捷鍵

```text
←          上一影格
→          下一影格
Space      播放或暫停
T          編輯頂視尖端
S          編輯側視尖端
R          清除本影格人工修正
X          標記本影格無效
Enter      儲存並前往下一影格
```

---

### 20.4 修正紀錄

每次人工修改必須保存：

```text
correction_id
analysis_id
frame_id
camera_id
automatic_x_px
automatic_y_px
corrected_x_px
corrected_y_px
operator_id
created_at
reason
```

---

## 21. 最終二維位置解析

每一影格最終位置依以下優先順序決定：

```text
Manual
    ↓
Automatic 或 Estimated
    ↓
Interpolated
    ↓
Missing
```

人工修正具有最高優先權，但不得刪除原始自動偵測資料。

---

## 22. 三維位置估計

完成頂視與側視二維位置後，使用雙鏡頭投影矩陣進行三角化。

建議使用：

```python
cv2.triangulatePoints
```

輸入：

```text
P_top
P_side
top_point
side_point
```

輸出齊次座標後，轉換為：

```text
X
Y
Z
```

世界座標單位：

```text
millimeter
```

---

### 22.1 三維點資料

每一個三維點保存：

```text
frame_id
cycle_id
timestamp
top_x_px
top_y_px
side_x_px
side_y_px
x_mm
y_mm
z_mm
top_detection_type
side_detection_type
valid
```

---

### 22.2 世界座標系

系統需明確定義世界座標系：

```text
原點
X 軸方向
Y 軸方向
Z 軸方向
單位
```

建議：

```text
原點：花盆或植物基部中心
X：水平方向
Y：水平深度方向
Z：垂直向上
單位：mm
```

座標系必須保存於 Calibration Profile。

---

## 23. 重投影誤差

完成三維點後，將三維點重新投影至兩台相機。

計算：

```text
top_reprojection_error_px
side_reprojection_error_px
```

誤差為：

```text
偵測二維位置
與
三維點重新投影位置
之間的像素距離
```

---

### 23.1 OpenCV 方法

可使用：

```python
cv2.projectPoints
```

或投影矩陣自行計算。

---

### 23.2 統計內容

結果需顯示：

- 頂視平均重投影誤差
- 側視平均重投影誤差
- 整體平均重投影誤差
- 標準差
- 最大誤差
- 每影格誤差
- 誤差大於 10 px 的影格數
- 誤差大於 10 px 的比例

---

### 23.3 論文比較基準

論文報告：

```text
植物尖端正確取得率：86% 至 98%
平均重投影誤差：約 3.7 px
推估三維定位誤差：約 0.5 cm
人工修正比例：約 8.3%
```

這些數值只能作為方法重現的比較基準。

不得預設 CHLOROCULUS 一定能取得相同結果。

實際結果會受到：

- 相機解析度
- 鏡頭
- 相機位置
- 植物種類
- 光照
- 背景
- 校正覆蓋
- 遮擋
- 尖端與莖重疊
- 影像同步

影響。

---

## 24. 結果視覺化

路由：

```text
/analysis/[analysisId]/results
```

---

### 24.1 頂視結果

顯示：

- 頂視影像
- 尖端位置
- 二維尖端軌跡
- Automatic 點
- Estimated 點
- Interpolated 點
- Manual 點

---

### 24.2 側視結果

顯示：

- 側視影像
- 尖端位置
- 二維尖端軌跡
- Epipolar Line
- Minimum Path
- 各偵測類型

---

### 24.3 三維軌跡

顯示：

- X、Y、Z 軌跡
- 起始點
- 結束點
- 植物基部
- 頂視相機位置
- 側視相機位置
- 高重投影誤差點
- 人工修正點

第一版只需要三維軌跡顯示，不做週期、自相關或頻率分析。

---

### 24.4 誤差圖表

顯示：

- 頂視誤差隨時間變化
- 側視誤差隨時間變化
- 誤差大於 10 px 的位置
- 誤差分布
- 平均值與標準差

---

## 25. 偵測統計

每個 Analysis Run 統計：

```text
Automatic
Estimated
Interpolated
Manual
Missing
Invalid
```

分別顯示：

- 頂視數量
- 頂視比例
- 側視數量
- 側視比例
- 整體數量
- 整體比例

統計方式應能與論文的 Automatic、Manual、Estimated、Interpolated 分類比較。

---

## 26. 分析輸出

每個 Analysis Run 至少輸出：

```text
analysis.json
parameters.json
frame_pairs.csv
top_detections.csv
side_detections.csv
manual_corrections.json
resolved_top_positions.csv
resolved_side_positions.csv
trajectory_3d.csv
reprojection_errors.csv
detection_summary.json
calibration_reference.json
```

---

### 26.1 `trajectory_3d.csv`

欄位：

```csv
frame_id,cycle_id,timestamp,top_x_px,top_y_px,side_x_px,side_y_px,x_mm,y_mm,z_mm,top_detection_type,side_detection_type,top_reprojection_error_px,side_reprojection_error_px,valid
```

---

### 26.2 `top_detections.csv`

欄位：

```csv
frame_id,timestamp,candidate_count,selected_x_px,selected_y_px,detection_type,valid
```

---

### 26.3 `side_detections.csv`

欄位：

```csv
frame_id,timestamp,candidate_count,selected_x_px,selected_y_px,detection_type,valid
```

---

## 27. 資料夾結構

```text
data/
├─ captures/
│  └─ session_YYYY-MM-DD_NNN/
│
├─ calibration/
│  └─ calibration_YYYY-MM-DD_NNN/
│     ├─ calibration.json
│     ├─ top_intrinsics.json
│     ├─ side_intrinsics.json
│     ├─ stereo_extrinsics.json
│     ├─ selected_images.json
│     ├─ reprojection_errors.csv
│     └─ previews/
│
└─ analysis/
   └─ session_YYYY-MM-DD_NNN/
      └─ analysis_YYYY-MM-DD_NNN/
         ├─ analysis.json
         ├─ parameters.json
         ├─ frame_pairs.csv
         │
         ├─ detections/
         │  ├─ top_automatic.csv
         │  ├─ side_automatic.csv
         │  ├─ manual_corrections.json
         │  ├─ resolved_top.csv
         │  └─ resolved_side.csv
         │
         ├─ reconstruction/
         │  ├─ trajectory_3d.csv
         │  └─ reprojection_errors.csv
         │
         ├─ summaries/
         │  └─ detection_summary.json
         │
         ├─ overlays/
         │  ├─ top/
         │  └─ side/
         │
         └─ logs/
            └─ analysis.log
```

---

## 28. Analysis Run 狀態

狀態：

```text
draft
validating
ready
processing
needs_review
reviewing
reconstructing
completed
failed
cancelled
```

標準流程：

```text
draft
    ↓
validating
    ↓
ready
    ↓
processing
    ↓
needs_review
    ↓
reviewing
    ↓
reconstructing
    ↓
completed
```

若使用者選擇不進行人工修正，可直接使用自動結果與插值結果進行三維重建，但需記錄：

```text
manual_review_completed: false
```

---

## 29. 後端模組規劃

在既有 FastAPI 後端新增：

```text
backend/
└─ app/
   ├─ api/
   │  ├─ analysis_routes.py
   │  └─ calibration_routes.py
   │
   ├─ analysis/
   │  ├─ __init__.py
   │  ├─ analysis_runner.py
   │  ├─ session_validator.py
   │  ├─ frame_pairing.py
   │  │
   │  ├─ calibration/
   │  │  ├─ camera_calibration.py
   │  │  ├─ stereo_calibration.py
   │  │  ├─ calibration_quality.py
   │  │  └─ calibration_storage.py
   │  │
   │  ├─ segmentation/
   │  │  ├─ mog2_background.py
   │  │  ├─ contour_processing.py
   │  │  └─ lighting_change.py
   │  │
   │  ├─ detection/
   │  │  ├─ top_tip_detection.py
   │  │  ├─ side_tip_detection.py
   │  │  ├─ candidate_selection.py
   │  │  ├─ epipolar_constraint.py
   │  │  └─ minimum_path.py
   │  │
   │  ├─ tracking/
   │  │  ├─ temporal_selection.py
   │  │  └─ linear_interpolation.py
   │  │
   │  ├─ reconstruction/
   │  │  ├─ triangulation.py
   │  │  ├─ reprojection.py
   │  │  └─ coordinate_system.py
   │  │
   │  ├─ review/
   │  │  └─ manual_corrections.py
   │  │
   │  └─ export/
   │     ├─ csv_export.py
   │     └─ json_export.py
   │
   ├─ models/
   │  ├─ analysis_models.py
   │  └─ calibration_models.py
   │
   ├─ repositories/
   │  ├─ analysis_repository.py
   │  └─ calibration_repository.py
   │
   └─ services/
      ├─ analysis_service.py
      └─ calibration_service.py
```

---

## 30. 前端模組規劃

在既有 Next.js 前端新增：

```text
frontend/
└─ src/
   ├─ app/
   │  ├─ capture/
   │  │  └─ page.js
   │  │
   │  ├─ analysis/
   │  │  ├─ page.js
   │  │  ├─ new/
   │  │  │  └─ page.js
   │  │  ├─ calibration/
   │  │  │  ├─ page.js
   │  │  │  └─ [calibrationId]/
   │  │  │     └─ page.js
   │  │  └─ [analysisId]/
   │  │     ├─ page.js
   │  │     ├─ review/
   │  │     │  └─ page.js
   │  │     └─ results/
   │  │        └─ page.js
   │  │
   │  └─ models/
   │     └─ page.js
   │
   ├─ features/
   │  ├─ MainNavigation/
   │  ├─ AnalysisDashboard/
   │  ├─ AnalysisSetup/
   │  ├─ Calibration/
   │  ├─ FramePairing/
   │  ├─ TipReview/
   │  ├─ TrajectoryViewer/
   │  └─ ReprojectionErrors/
   │
   └─ lib/
      ├─ analysisApi.js
      └─ calibrationApi.js
```

---

## 31. 分析首頁

路由：

```text
/analysis
```

顯示：

- 可分析的 Capture Sessions
- Session 日期
- 頂視影像數量
- 側視影像數量
- 已配對影格數
- Calibration 狀態
- Analysis Run
- 分析狀態
- 人工修正狀態
- 平均重投影誤差
- 建立新分析
- 繼續修正
- 查看結果
- 匯出結果

---

## 32. 新增分析流程

路由：

```text
/analysis/new
```

步驟：

### Step 1：選擇 Capture Session

顯示：

- Session ID
- 日期
- 頂視影像數
- 側視影像數
- 影格配對狀態
- 是否具備分析條件

### Step 2：選擇 Calibration Profile

顯示：

- Calibration ID
- 相機識別
- 解析度
- 建立日期
- 個別相機誤差
- 雙鏡頭誤差
- 是否有效

### Step 3：設定分析範圍

設定：

- 起始影格
- 結束影格
- 頂視 ROI
- 側視 ROI
- Frame Offset

### Step 4：設定論文方法參數

設定：

- MOG2 參數
- 輪廓面積門檻
- Morphology Kernel
- Lighting Change Area
- Lighting Change Estimate Time
- Epipolar Line 距離門檻
- Minimum Path 參數

### Step 5：建立 Analysis Run

顯示：

- 輸入摘要
- 方法版本
- Calibration
- 影格數量
- 輸出路徑

---

## 33. API 規劃

瀏覽器只呼叫 Next.js BFF 提供的同源 API。

FastAPI 硬體與分析端點不直接暴露給瀏覽器。

---

### 33.1 Analysis Run

```text
GET    /api/analysis
POST   /api/analysis
GET    /api/analysis/{analysis_id}
DELETE /api/analysis/{analysis_id}
```

---

### 33.2 分析控制

```text
POST /api/analysis/{analysis_id}/validate
POST /api/analysis/{analysis_id}/start
POST /api/analysis/{analysis_id}/cancel
POST /api/analysis/{analysis_id}/retry
POST /api/analysis/{analysis_id}/reconstruct
```

---

### 33.3 影格資料

```text
GET /api/analysis/{analysis_id}/frames
GET /api/analysis/{analysis_id}/frames/{frame_id}
GET /api/analysis/{analysis_id}/frame-pairs
```

---

### 33.4 人工修正

```text
POST   /api/analysis/{analysis_id}/corrections
DELETE /api/analysis/{analysis_id}/corrections/{correction_id}
```

---

### 33.5 結果

```text
GET /api/analysis/{analysis_id}/trajectory
GET /api/analysis/{analysis_id}/reprojection-errors
GET /api/analysis/{analysis_id}/detection-summary
GET /api/analysis/{analysis_id}/export
```

---

### 33.6 Calibration

```text
GET    /api/calibrations
POST   /api/calibrations
GET    /api/calibrations/{calibration_id}
DELETE /api/calibrations/{calibration_id}

POST /api/calibrations/{calibration_id}/detect-corners
POST /api/calibrations/{calibration_id}/solve-intrinsics
POST /api/calibrations/{calibration_id}/solve-stereo
POST /api/calibrations/{calibration_id}/validate
GET  /api/calibrations/{calibration_id}/report
```

---

## 34. 分析執行方式

分析數千張影像可能需要較長時間，不應在單一 HTTP Request 中同步完成。

初始版本使用：

```text
FastAPI Analysis Worker
+
SQLite Job State
```

不必在本階段引入：

- Redis
- Celery
- RabbitMQ
- 外部工作佇列

分析 Worker 不得阻塞：

- CHLOROCULUS 馬達安全控制
- 緊急停止
- 相機預覽
- Capture Session
- WebSocket 心跳

---

## 35. 即時進度

既有 WebSocket 狀態可增加：

```json
{
  "analysis": {
    "analysis_id": "analysis_2026-07-17_001",
    "status": "processing",
    "stage": "side_tip_detection",
    "current_frame": 1240,
    "total_frames": 4800,
    "progress": 0.2583
  }
}
```

分析階段名稱：

```text
validating
pairing_frames
calibrating
initializing_background
detecting_top_tip
detecting_side_tip
interpolating
waiting_for_review
triangulating
calculating_reprojection_error
exporting
completed
```

---

## 36. JSON 設定

所有設定一律使用 JSON，不使用 YAML。

新增：

```text
backend/config/analysis.json
backend/config/calibration.json
```

---

### 36.1 `analysis.json`

```json
{
  "method": {
    "name": "top_side",
    "reference": "Ruiz-Melero et al. 2024"
  },
  "synchronization": {
    "primary_key": "cycle_id",
    "timestamp_tolerance_ms": 1000,
    "manual_frame_offset": 0,
    "keep_unpaired_frames": true
  },
  "segmentation": {
    "method": "mog2",
    "history": null,
    "variance_threshold": null,
    "detect_shadows": false,
    "opening_kernel_size": null,
    "closing_kernel_size": null,
    "erosion_kernel_size": null,
    "minimum_top_contour_area_px": null,
    "minimum_side_contour_area_px": null
  },
  "lighting_change": {
    "lighting_change_area_px": null,
    "lighting_change_est_time_frames": null
  },
  "top_detection": {
    "roi": null
  },
  "side_detection": {
    "roi": null,
    "maximum_epipolar_distance_px": null
  },
  "interpolation": {
    "method": "linear"
  },
  "reprojection": {
    "high_error_threshold_px": 10.0
  }
}
```

所有為 `null` 的資料相依參數，必須在第一次實驗資料測試後決定，不預先虛構為論文未指定的固定值。

---

### 36.2 `calibration.json`

```json
{
  "individual_calibration": {
    "pattern": "chessboard",
    "pattern_columns": 10,
    "pattern_rows": 7,
    "board_width_cm": 59.4,
    "board_height_cm": 84.1
  },
  "stereo_calibration": {
    "pattern": "chessboard",
    "board_width_cm": 42.0,
    "board_height_cm": 59.4
  },
  "quality": {
    "store_error_per_image": true,
    "store_point_coverage": true
  }
}
```

若實體棋盤規格與論文不同，必須修改為實際測量值，不能只保留論文數字。

---

## 37. Python 相依套件

第一版分析功能主要使用：

```text
opencv-python
numpy
scipy
pandas
```

既有 FastAPI 系統繼續使用：

```text
fastapi
uvicorn
pydantic
sqlalchemy
aiofiles
```

視覺化可由前端實作，或由後端輸出標準 JSON 資料。

第一版不需要：

```text
PyTorch
TensorFlow
Ultralytics
Detectron2
COLMAP Python Wrapper
3DGS Training Library
```

---

## 38. 錯誤處理

系統需處理：

- Session 不存在
- 頂視影像不存在
- 側視影像不存在
- 影格無法配對
- 解析度與 Calibration 不一致
- Calibration 不存在
- Calibration 已失效
- 棋盤角點偵測失敗
- 個別相機校正失敗
- 雙鏡頭校正失敗
- 背景模型無法穩定
- 植物輪廓不存在
- 頂視尖端候選不存在
- 側視輪廓不在 Epipolar Line 附近
- Minimum Path 無法建立
- 缺失區段無法插值
- 三角化失敗
- 齊次座標無效
- 重投影誤差異常
- 寫入分析資料失敗
- 分析被取消
- 程式非正常中止

錯誤應：

- 寫入 Analysis Log
- 顯示於 Web 介面
- 保存目前進度
- 不修改 Capture Session
- 不使 FastAPI 整體崩潰
- 不影響 CHLOROCULUS 緊急停止

---

## 39. 測試

### 39.1 單元測試

```text
test_frame_pairing.py
test_camera_calibration.py
test_stereo_calibration.py
test_mog2_segmentation.py
test_lighting_change.py
test_top_tip_detection.py
test_epipolar_constraint.py
test_minimum_path.py
test_candidate_selection.py
test_linear_interpolation.py
test_triangulation.py
test_reprojection.py
```

---

### 39.2 整合測試

```text
test_analysis_creation.py
test_calibration_workflow.py
test_complete_detection_pipeline.py
test_manual_correction.py
test_reconstruction_workflow.py
test_analysis_export.py
```

---

### 39.3 基準資料集

需建立一組小型測試資料集，包含：

- 頂視影像
- 側視影像
- Calibration
- 已知人工尖端標記
- 已知影格配對
- 預期三維軌跡範圍

測試資料集不得包含完整長期實驗，以避免 Repository 過大。

---

## 40. 實作順序

### Milestone 1：頁面分類與分析骨架

- 新增 `[捕捉] [分析] [模型]` 導覽
- 將現有控制頁移至 `/capture`
- 建立 `/analysis`
- 建立 Analysis Run 資料模型
- 建立分析資料目錄
- 建立 API 骨架

---

### Milestone 2：影格配對

- 讀取 Capture Session
- 頂視與側視影像索引
- Cycle ID 配對
- Timestamp 配對
- Manual Frame Offset
- 配對結果檢視

---

### Milestone 3：相機校正

- 個別相機棋盤角點偵測
- 頂視相機校正
- 側視相機校正
- 雙鏡頭相機校正
- Projection Matrix
- Fundamental Matrix
- 重投影誤差
- Calibration Profile

---

### Milestone 4：頂視尖端偵測

- ROI
- MOG2
- 光照變化偵測
- 背景模型重設
- 輪廓取得
- 候選點
- 最近位置選擇
- Automatic 與 Estimated 分類

---

### Milestone 5：側視尖端偵測

- 側視 MOG2
- 側視輪廓
- Epipolar Line
- 輪廓篩選
- Minimum Path
- 候選位置
- Automatic 與 Estimated 分類

---

### Milestone 6：插值與人工修正

- Missing 區段
- Linear Interpolation
- Review 頁面
- 頂視人工點選
- 側視人工點選
- Manual Correction 儲存

---

### Milestone 7：三維重建

- 最終二維位置解析
- Triangulation
- 世界座標
- Reprojection
- 誤差統計
- 三維軌跡

---

### Milestone 8：結果與匯出

- 偵測類型統計
- 二維軌跡
- 三維軌跡
- 誤差圖表
- CSV
- JSON
- 完整測試

---

## 41. GOAL-02 非目標

本階段不處理：

- CHLOROCULUS EYE-ARM 多視角分析
- COLMAP
- Structure from Motion
- Multi-View Stereo
- 3D Gaussian Splatting
- NeRF
- 全株三維模型
- 點雲
- 網格模型
- 深度學習植物分割
- 深度學習尖端追蹤
- 多尖端追蹤
- 葉片追蹤
- 莖骨架追蹤
- Optical Flow
- Kalman Filter
- Particle Filter
- FFT
- Autocorrelation
- Circumnutation 週期自動分析
- 行為分類
- 支撐物選擇推論
- 植物意圖判定
- 植物意識判定
- 雲端分析
- 分散式分析

以上內容需等論文方法成功重現後，再於後續 GOAL 中加入。

---

## 42. 驗收條件

GOAL-02 達到以下條件即視為完成：

1. 系統具有 `[捕捉] [分析] [模型]` 三個頂層入口。
2. 既有捕捉頁面移至 `/capture` 且功能不退化。
3. `/analysis` 可列出可分析的 Capture Sessions。
4. 系統可配對頂視與側視影像。
5. 系統支援 Manual Frame Offset。
6. 系統可完成頂視相機個別校正。
7. 系統可完成側視相機個別校正。
8. 系統可完成雙鏡頭相機校正。
9. 系統可保存 Camera Matrix 與 Distortion Coefficients。
10. 系統可保存 R、t、E、F 與 Projection Matrices。
11. 系統可顯示校正重投影誤差。
12. 系統可使用 MOG2 分割頂視植物輪廓。
13. 系統可偵測光照切換並重設背景模型。
14. 系統可產生頂視尖端候選點。
15. 系統可依論文規則選擇頂視尖端。
16. 系統可由頂視尖端計算側視 Epipolar Line。
17. 系統可使用 Epipolar Line 篩選側視輪廓。
18. 系統可使用 Minimum Path Algorithm 產生側視尖端候選。
19. 系統可依論文規則選擇側視尖端。
20. 系統可使用 Linear Interpolation 補足缺失影格。
21. 系統可區分 Automatic、Estimated、Interpolated 與 Manual。
22. 使用者可在 Web 介面人工修正頂視位置。
23. 使用者可在 Web 介面人工修正側視位置。
24. 人工修正不會覆寫自動偵測結果。
25. 系統可使用雙鏡頭三角化取得 X、Y、Z。
26. 系統可計算頂視與側視重投影誤差。
27. 系統可標記誤差大於 10 px 的影格。
28. 系統可顯示頂視二維軌跡。
29. 系統可顯示側視二維軌跡。
30. 系統可顯示植物尖端三維軌跡。
31. 系統可輸出 `trajectory_3d.csv`。
32. 系統可輸出偵測類型統計。
33. 系統可輸出重投影誤差資料。
34. Capture Session 原始資料不會被分析修改。
35. 所有分析設定均使用 JSON。
36. 分析工作不阻塞馬達緊急停止。
37. 第一版演算法未混入深度學習或其他追蹤方法。
38. 分析結果不直接宣稱植物具有或不具有意識。

---

## 43. 研究定位

GOAL-02 的目的不是透過一條三維軌跡直接證明植物具有意識。

本階段先建立可靠的觀測與測量方法，使植物原本難以由人類直接察覺的緩慢運動，能被轉換為：

- 可檢查的二維位置
- 可修正的尖端標記
- 可比較的三維座標
- 可量化的定位誤差
- 可重現的時間序列
- 可追溯的分析結果

只有在這套基準方法成功建立後，後續研究才可能進一步比較：

- 有無支撐物時的運動差異
- 不同植物個體的軌跡差異
- 植物是否調整接近支撐物的運動
- 植物運動是否存在持續性的組織結構
- 哪些現象可由生長與向性解釋
- 哪些現象值得進一步以其他模型檢驗

分析結果是觀察植物內部性與感知問題的材料，不是預先設定的答案。

---

## 44. 參考研究

Ruiz-Melero, D. R., Ponkshe, A., Calvo, P., & García-Mateos, G.
The Development of a Stereo Vision System to Study the Nutation Movement of Climbing Plants.
Sensors, 2024, 24, 747.
DOI: 10.3390/s24030747

存放於：goals\references\2024 The Development of a Stereo Vision System to Study the Nutation Movement of Climbing Plants.pdf

GOAL-02 第一版重現以下方法：

- 頂視與側視雙鏡頭影像
- 個別相機校正
- 雙鏡頭相機校正
- Pinhole Camera Model
- 徑向與切向鏡頭畸變
- Projection Matrix
- Essential Matrix
- Fundamental Matrix
- Gaussian Mixture Background Segmentation
- 光照變化後重設背景模型
- 頂視尖端候選點偵測
- 最近前一位置候選選擇
- Epipolar Line
- 側視輪廓篩選
- Minimum Path Algorithm
- Linear Interpolation
- Manual Correction
- Stereo Triangulation
- Reprojection Error
- Automatic、Estimated、Interpolated、Manual 分類
- 三維植物尖端軌跡


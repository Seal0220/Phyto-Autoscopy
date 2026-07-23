
# GOAL-05 — Round-based Multi-view Plant Reconstruction and Tip Analysis

# Phyto-Autoscopy

### 以每輪多視角影像同步建立三維植物模型、尖端標記與跨輪運動資料

---

## 1. 目標

重構目前「新增分析」的第 3、4、5 步，將既有以 ROI、MOG2 背景分割、雙鏡頭尖端追蹤與旋臂局部精修為核心的分析流程，改為：

```text
每一 Round
→ 讀取同一 Round 的俯視、側視與旋臂影像
→ 每張影像套用所屬實體相機的內參並去畸變
→ 使用 ArUco 建立每張影像的公制世界座標姿態
→ 使用多視角特徵精修相機姿態與建立稀疏幾何
→ 共同建立每個 Round 的三維植物模型
→ 同步建立可分析的三維尖端標記
→ 將各 Round 的尖端標記串接為時間軌跡
```

本 GOAL 的正式輸出不只是可視化模型，而是同時包含：

- 每個 Round 的三維 Gaussian Splatting 模型
- 每個 Round 的植物點雲
- 每個 Round 的植物骨架
- 每個 Round 的三維尖端標記
- 每個尖端標記的信心與品質資料
- 各影像中的尖端標記重投影
- 跨 Round 的三維尖端標記軌跡
- 可供後續表型與運動分析使用的結構化資料

新的完整多視角流程不得再以不同 Round 的前後影像相減作為植物或尖端辨識的主要方法。

新的完整多視角流程不得再要求使用者手動設定 ROI。

---

## 2. 術語規則

### 2.1 使用者可見名稱

所有使用者可見介面、文件、通知、圖表、匯出欄位、狀態與錯誤訊息中，`Landmark` 一律顯示為：

```text
標記
```

植物尖端的正式中文名稱為：

```text
尖端標記
```

使用者可見內容禁止顯示：

```text
Landmark
Tip Landmark
尖端 Landmark
```

統一改為：

```text
標記
尖端標記
三維尖端標記
尖端標記信心
尖端標記品質
尖端標記軌跡
尖端標記人工修正
尖端標記重投影誤差
```

### 2.2 使用範例

```text
建立三維尖端標記
正在精修尖端標記
尖端標記信心不足
等待確認尖端標記
跨 Round 尖端標記軌跡
```

### 2.3 內部程式識別碼

內部 Python 類別、資料表、JSON 欄位與 API 識別碼可使用穩定英文名稱，例如：

```text
TipLandmark
tip_landmark_id
tip_landmark
tip_confidence
```

但前端不得直接將內部識別碼顯示給使用者。

所有內部英文狀態都必須經過前端顯示映射。

---

## 3. 現有新增分析流程

目前新增分析共有五步：

```text
1. 選擇紀錄
2. 配置設定
3. 分析範圍
4. 方法參數
5. 建立分析
```

目前第 1 步與第 2 步已負責：

- 選擇 Record
- 顯示 Record 根目錄
- 顯示 Record 捕捉配置
- 選取擷取模式
- 選擇分析視角
- 掃描影像來源
- 顯示各相機影像數量
- 顯示影像解析度
- 驗證來源是否可分析

上述責任應保留。

目前第 3、4、5 步存在以下問題：

- 以全域影格索引選擇分析範圍
- 使用人工影格偏移強制配對
- 要求設定俯視與側視 ROI
- 使用動態 ROI
- 要求人工輸入植物基部像素位置
- 方法參數仍以 MOG2、Morphology 與 Minimum Path 為主
- 旋臂只被視為俯視與側視結果的局部精修來源
- 每個雙相機影格組最多只關聯一張旋臂影像
- 同一 Round 的其他旋臂角度未被完整保存給模型建立
- 尚未建立「每個 Round 一個完整模型」的資料架構
- 尚未建立模型與尖端標記的聯合分析流程

---

## 4. 重構後新增分析流程

重構後改為四步：

```text
1. 選擇紀錄
2. 配置設定
3. 重建與尖端分析
4. 確認並建立
```

調整方式：

```text
原第 1 步「選擇紀錄」
→ 保留

原第 2 步「配置設定」
→ 保留並擴充 Round readiness

原第 3 步「分析範圍」
→ 完整移除

原第 4 步「方法參數」
→ 改寫為新第 3 步「重建與尖端分析」

原第 5 步「建立分析」
→ 改寫為新第 4 步「確認並建立」
```

---

# 5. 移除原第 3 步「分析範圍」

## 5.1 移除整個步驟

刪除：

```text
frontend/src/features/Analysis/components/AnalysisSetupRangeStep.js
```

刪除新增分析頁面中對該步驟的：

- import
- render branch
- props
- state 更新
- 驗證
- payload 建立
- 摘要顯示
- 測試

目前：

```text
currentStep === 3
→ AnalysisSetupRangeStep
```

應改為：

```text
currentStep === 3
→ AnalysisSetupReconstructionStep
```

## 5.2 移除影格範圍

刪除：

```text
startFrame
endFrame
start_frame
end_frame
analysisFrameCount
```

分析輸入範圍不再由人工填寫全域起始影格與結束影格決定。

本次分析的輸入改由以下項目共同決定：

```text
Record
＋第 2 步選取的 mode_ids
＋第 2 步啟用的 camera sources
```

每個已選模式中，所有通過驗證的 Round 都應納入分析。

未來若需要只分析部分 Round，應建立具有 Round 語意的選取介面，例如：

```text
選擇 Round 1–20
排除 Round 7
只分析指定 Round
```

不得再以不具模式與 Round 語意的全域影格索引處理。

## 5.3 移除人工影格偏移

刪除：

```text
manualFrameOffset
manual_frame_offset
frame_offset
manually_aligned
```

目前新的捕捉儲存結構已有：

- Record
- mode
- round
- snapshot
- timestamp
- camera ID
- rotating angle
- capture metadata

分析必須依正式資料階層、metadata 與時間戳配對。

無法可靠歸屬到相同 Round 或 snapshot 的影像應：

- 標示為未配對
- 保存失敗原因
- 從該 Round 的有效視角中排除
- 不得透過人工索引偏移強制配對

## 5.4 移除所有 ROI

前端刪除：

```text
topRoi
sideRoi
AnalysisSetupRoiFields
ROI_FIELDS
updateRoi
onRoiChange
topUpdateRoi
sideUpdateRoi
topRoiUpdateMargin
sideRoiUpdateMargin
```

後端刪除：

```text
Roi
top_roi
side_roi
top_detection.roi
side_detection.roi
update_roi
roi_update_margin_px
```

設定檔刪除：

```text
top_detection.roi
side_detection.roi
top_detection.update_roi
side_detection.update_roi
top_detection.roi_update_margin_px
side_detection.roi_update_margin_px
```

刪除所有：

- ROI 解析
- ROI 邊界驗證
- ROI 裁切
- ROI 座標位移
- 動態 ROI 更新
- ROI 摘要
- ROI 測試

## 5.5 有效像素遮罩不屬於 ROI

系統可以保留自動產生的：

```text
valid_pixel_mask
exclusion_mask
plant_mask
```

其用途分別為：

### `valid_pixel_mask`

排除：

- 魚眼去畸變產生的黑邊
- 無有效影像資料區域
- 重新映射後的無效像素

### `exclusion_mask`

排除：

- 固定裝置結構
- 不應進入植物模型的已知區域
- ArUco Marker 本身
- 相機預覽疊圖
- 壞點或永久遮擋區域

### `plant_mask`

表示單張影像中的植物語意區域。

上述遮罩皆由系統自動產生或由裝置設定推導，不得重新變成人工矩形 ROI。

## 5.6 移除人工植物基部像素

刪除：

```text
topPlantBaseX
topPlantBaseY
sidePlantBaseX
sidePlantBaseY
top_detection.plant_base
side_detection.plant_base
```

植物基部不得再以不同相機畫面中的人工像素位置輸入。

若尖端分析需要植物基部，應使用：

```text
平台世界原點
＋植物中心或盆器中心的世界座標偏移
```

正式資料：

```text
plant_base_world_mm = [x, y, z]
```

再依每張影像的內參與外參投影至去畸變影像座標。

---

# 6. Round 作為正式分析單位

## 6.1 正式分析單位

新的主要分析單位為：

```text
Analysis Round
```

每個 Round 對應一個模式中的一輪捕捉。

正式識別至少包含：

```text
record_id
mode_id
round_id
```

建議唯一鍵：

```text
<record_id>:<mode_id>:<round_id>
```

不得再以全域 `frame_id` 作為模型建立的主要資料單位。

## 6.2 Round 內容

每個 Round 可包含：

```text
Round
├─ top views
├─ side views
└─ rotating views
```

每張影像都必須保存為獨立的 Analysis View。

每一個 Analysis View 至少包含：

```text
view_id
record_id
mode_id
round_id
snapshot_id
capture_id
camera_id
timestamp
relative_path
absolute_path
angle_deg
motor_position_deg
image_width
image_height
image_hash
```

## 6.3 模式與 Round 分離

不同 mode 中即使存在相同 Round 編號，也不得混合。

例如：

```text
AngleInterval.01 / round.01
SpecificAngles.02 / round.01
```

必須被視為兩個不同的 Analysis Round。

## 6.4 Continuous 模式

`continuous_interval` 或其他沒有旋臂 Round 概念的模式使用：

```text
round.00
```

此模式若包含長時間連續影像，不應直接把整段視為同一個靜態 3DGS 場景。

處理方式必須明確分流：

### 固定雙相機模式

```text
top + side
→ 尖端標記時間追蹤
```

### 旋臂多視角模式

```text
每個正式 rotating Round
→ 建立獨立模型與尖端標記
```

若 `round.00` 中沒有形成可辨識的多視角掃描，不得宣稱可以建立完整環繞模型。

## 6.5 旋臂影像

同一 Round 的所有有效旋臂角度都必須保留。

禁止繼續使用：

```text
一組 top / side pair
→ 只選時間最近的一張 rotating image
```

旋臂影像應依正式 metadata 歸入 Round。

角度只用於：

- 視角排序
- 覆蓋率分析
- 重複角度判定
- 馬達姿態先驗
- 捕捉異常檢查
- 相機姿態合理性檢查

不同 Round 的相同角度影像不得互相做像素相減。

## 6.6 固定相機重複影像

若同一 Round 中 top 或 side 被重複拍攝多次，而相機姿態沒有改變，這些影像不應全部以相同姿態加入 3DGS，避免固定視角被過度加權。

系統應：

1. 根據清晰度、曝光與 ArUco 重投影誤差選擇代表影像；或
2. 將重複影像作為尖端候選共識、影像品質與靜態性檢查來源。

正式模型至少加入：

```text
一張有效 top 代表影像
一張有效 side 代表影像
全部有效且角度不重複的 rotating images
```

## 6.7 Round 靜態性

3DGS 假設同一批訓練影像描述近似相同的靜態場景。

每個 Round 必須保存：

```text
round_started_at
round_ended_at
round_duration_seconds
view_count
rotating_view_count
static_scene_score
```

系統應檢查：

- Round 捕捉總時長
- 相鄰旋臂影像中的植物位移
- 固定 top／side 影像在 Round 前後的變化
- 風或震動造成的植物非剛性運動
- 曝光或光照是否突變

若植物在單一 Round 中明顯移動：

- 顯示警告
- 降低模型品質
- 可排除明顯不一致影像
- 保存非剛性運動指標
- 不得靜默產生看似正常的模型

---

# 7. 每張影像必須先套用內參

## 7.1 不可跳過的第一階段

任何影像進入以下程序前：

- ArUco 偵測
- 相機姿態估算
- 特徵提取
- 特徵匹配
- 植物分割
- 尖端候選偵測
- 三角測量
- 3DGS
- 點雲建立
- 骨架建立
- 重投影誤差
- 人工修正

都必須先載入對應實體相機的內參並完成去畸變。

正式順序：

```text
raw image
→ identify camera_id
→ load camera intrinsics
→ adapt intrinsics to image resolution
→ fisheye undistortion
→ generate valid pixel mask
→ all later processing
```

## 7.2 相機與內參對應

```text
top views
→ top intrinsics

side views
→ side intrinsics

all rotating views
→ rotating intrinsics
```

旋臂在不同角度拍攝時：

```text
內參 K、D 不變
外參 R、t 隨每張影像改變
```

不得為不同旋臂角度建立不同內參。

## 7.3 內參固化

建立 Analysis Run 時，必須將當下所有已啟用相機的內參固化至：

```text
intrinsics_snapshot
```

Snapshot 至少包含：

```text
camera_id
camera_model
camera_matrix
distortion_coefficients
calibration_image_width
calibration_image_height
analysis_image_width
analysis_image_height
adapted_camera_matrix
undistorted_camera_matrix
calibration_reprojection_error_px
intrinsics_created_at
intrinsics_updated_at
intrinsics_version
```

Analysis Run 建立後，即使系統中的正式內參更新，既有 Run 仍使用建立當下的 snapshot。

## 7.4 解析度調整

若分析影像解析度與校正解析度不同，系統必須檢查：

- 長寬比是否一致
- 是否只進行等比例縮放
- 是否經過裁切
- 是否使用相同相機模式
- 是否改變感光元件讀取區域

只有等比例縮放時，才可按比例調整：

```text
fx
fy
cx
cy
```

若長寬比、裁切區域或感光元件模式不同，現有內參應標記為不相容並阻止分析。

## 7.5 Fisheye 去畸變

目前正式相機模型為 `opencv_fisheye` 時，必須使用：

```python
new_camera_matrix = cv2.fisheye.estimateNewCameraMatrixForUndistortRectify(
    camera_matrix,
    distortion_coefficients,
    image_size,
    np.eye(3),
    balance=balance,
)

map_x, map_y = cv2.fisheye.initUndistortRectifyMap(
    camera_matrix,
    distortion_coefficients,
    np.eye(3),
    new_camera_matrix,
    image_size,
    cv2.CV_32FC1,
)

undistorted_image = cv2.remap(
    raw_image,
    map_x,
    map_y,
    interpolation=cv2.INTER_LINEAR,
)
```

不得將 fisheye 校正結果直接交給：

```python
cv2.undistort(...)
```

## 7.6 Remap 快取

每個 Analysis Run 依以下鍵快取 remap：

```text
camera_id
intrinsics_version
image_width
image_height
undistortion_balance
```

快取內容：

```text
map_x
map_y
new_camera_matrix
valid_pixel_mask
```

同一實體相機、同一解析度與同一內參版本的影像共用 remap。

## 7.7 統一座標空間

所有後續二維資料必須使用：

```text
undistorted image coordinate space
```

包括：

```text
aruco_corners
feature_points
plant_masks
tip_candidates
manual_corrections
reprojection_points
overlays
```

Run metadata 必須記錄：

```text
coordinate_space = "undistorted"
```

禁止在同一 Analysis Run 中混用：

```text
原始畸變座標
去畸變座標
```

## 7.8 原始資料保護

原始捕捉影像保持唯讀。

去畸變影像、遮罩與診斷圖像寫入 Analysis Run 的衍生資料目錄。

不得覆蓋原始 Record 影像。

---

# 8. ArUco 世界座標姿態

## 8.1 ArUco Layout Snapshot

建立 Analysis Run 時，固化目前 ArUco 平台設定：

```text
aruco_layout_snapshot
```

至少包含：

```text
dictionary
marker_ids
marker_size_mm
marker_corner_world_coordinates
marker_orientation
world_origin
world_axes
unit
layout_version
```

世界座標固定為：

```text
原點：植物平台中心
X：平台水平方向
Y：平台深度方向
Z：垂直向上
單位：mm
```

## 8.2 Marker 角點

外參估算必須使用每個 Marker 的四個角點。

不得只使用 Marker 中心點。

每個 Marker 的世界資料應保存完整角點座標：

```text
top_left_world
top_right_world
bottom_right_world
bottom_left_world
```

Marker 在平台上的安裝方向必須已知。

建議四個 Marker 使用相同物理方向並固定於同一張剛性模板。

## 8.3 偵測順序

ArUco 必須在去畸變影像上偵測：

```text
undistorted image
→ detect ArUco corners
→ match known marker world corners
→ solvePnP
→ calculate camera pose in world coordinates
→ calculate reprojection quality
```

使用：

```text
undistorted camera matrix
distortion coefficients = zero
```

不得將原始影像中的 ArUco 角點與去畸變後相機矩陣混用。

## 8.4 Top 與 Side

top 與 side 雖然為固定相機，每張影像仍要執行：

- ArUco 可見性檢查
- 姿態估算
- 重投影誤差計算
- 與固定姿態基準比較

整個 Analysis Run 可從有效姿態建立：

```text
robust fixed pose
```

可使用：

- robust median
- robust mean
- RANSAC
- constrained bundle adjustment

若某張固定相機影像的姿態明顯偏離基準：

- 優先使用該張影像自己的有效 ArUco 姿態
- 標記支架可能發生位移
- 保存姿態偏差
- 不得靜默套用已失效的固定姿態

## 8.5 Rotating

每一張 rotating image 都必須估算獨立外參。

馬達角度只能作為：

- 姿態初始值
- 相機移動方向先驗
- 視角排序
- 合理性檢查
- ArUco 部分遮擋時的弱約束

馬達角度不得直接取代 ArUco 所求得的最終外參。

## 8.6 ArUco 不可見

當部分影像看不到足夠 ArUco 時，可依以下順序補足姿態：

```text
1. ArUco 直接姿態
2. 同 Round 多視角特徵匹配
3. 相鄰旋臂姿態插值
4. 馬達運動模型先驗
```

補足後的姿態來源必須明確標記：

```text
aruco
feature_refined
motor_prior
interpolated
invalid
```

不得將估計姿態偽裝成 ArUco 直接量測。

## 8.7 姿態精修

同一 Round 的所有相機姿態可以進行聯合精修：

```text
ArUco world poses
＋ multi-view feature correspondences
＋ motor pose priors
→ constrained bundle adjustment
```

ArUco 世界點、世界軸與公制尺度必須保持固定，避免最佳化後產生：

- 世界座標漂移
- 尺度漂移
- 軸方向改變
- 不同 Round 無法直接比較

## 8.8 「對齊」的正式定義

ArUco 對齊在本 GOAL 中指：

> 將每張相機影像的相機姿態註冊至同一個三維世界座標。

不是將不同視角影像 warp 成相同的二維畫面。

3DGS 必須保留各影像原本的觀察方向，只使用：

- 去畸變影像
- 相機內參
- 相機外參
- 公制世界座標

禁止為了多視角建模，將 top、side 與 rotating 影像扭曲成同一張二維視圖。

---

# 9. 新第 3 步「重建與尖端分析」

## 9.1 取代原方法參數頁

原第 4 步目前包含：

- MOG2 背景分割
- Morphology
- 光照切換
- 植物基部像素
- 動態 ROI
- Epipolar Line
- Minimum Path
- 線性插值
- 舊式雙固定相機尖端追蹤

上述內容不得繼續作為完整多視角分析方法的主要參數頁。

新的第 3 步名稱：

```text
重建與尖端分析
```

## 9.2 分析方法

重構後正式方法：

### `round_multiview`

使用：

```text
top
side
rotating
```

輸出：

- 每 Round 三維 Gaussian 模型
- 每 Round 植物點雲
- 每 Round 植物骨架
- 每 Round 三維尖端標記
- 跨 Round 尖端標記軌跡

### `top_side_tip_only`

僅使用：

```text
top
side
```

輸出：

- top 與 side 二維尖端候選
- 雙視角三角化尖端標記
- 跨時間尖端標記軌跡

此模式不得宣稱會建立完整的環繞三維植物模型。

## 9.3 方法推導

第 2 步的 rotating 啟用狀態決定分析方法：

```text
rotating enabled
→ round_multiview

rotating disabled
→ top_side_tip_only
```

前端不必再額外顯示重複的分析方法按鈕。

## 9.4 旋臂的正式角色

旋臂不是俯視與側視三角化結果的事後補丁。

旋臂應作為：

```text
完整三維植物模型的主要環繞影像來源
```

top 與 side 則提供：

- 上方與側方補充視角
- 固定穩定參考
- 尖端標記的穩定二維觀測
- 尺度與姿態品質檢查
- 旋臂遮擋區域的補充

完整多視角模式不得再使用含糊名稱：

```text
頂+側+環繞精修
```

正式顯示名稱建議：

```text
每輪多視角三維重建
```

## 9.5 模型品質

提供三種品質 preset：

```text
預覽
標準
高品質
```

每個 preset 對應：

- 輸入影像縮放
- 3DGS iteration 數
- Gaussian densification
- 最大 Gaussian 數
- 模型輸出精度
- checkpoint 間隔
- 預期 GPU 記憶體
- 預期處理時間

一般介面不直接顯示大量底層訓練參數。

## 9.6 姿態精修

固定顯示：

```text
使用 ArUco 世界姿態
```

可設定：

```text
使用多視角 Bundle Adjustment 精修
```

ArUco 世界姿態不得關閉。

Bundle Adjustment 預設啟用。

若精修失敗，可回退至 ArUco 姿態，但必須保存警告與品質差異。

## 9.7 背景處理

預設策略：

```text
保留部分固定背景特徵協助姿態與模型初始化
→ 模型建立完成後移除背景 Gaussian
```

可設定：

- 是否產生植物遮罩
- 是否在訓練 loss 中使用植物遮罩
- 是否保留原始完整模型
- 是否輸出純植物模型
- 是否保存背景模型
- 是否輸出純植物點雲

不得使用不同 Round 的前後影像相減產生植物遮罩。

## 9.8 尖端分析

完整多視角模式下，尖端標記固定建立。

可設定：

- 最低尖端標記信心
- 最低支持視角數
- 最大容許重投影誤差
- 是否使用模型骨架精修
- 是否使用上一 Round 尖端標記作為弱時序先驗
- 是否在低信心時等待人工確認
- 是否輸出所有二維候選
- 是否保存重投影 overlay

## 9.9 輸出選項

可設定：

- 保存 Gaussian 模型
- 輸出完整點雲
- 輸出純植物點雲
- 輸出植物骨架
- 輸出每 Round 尖端標記 JSON
- 輸出完整尖端標記軌跡 CSV
- 保存模型預覽
- 保存重投影 overlay
- 保存診斷資料
- 保存 checkpoint

## 9.10 進階設定

進階設定預設折疊，可包含：

```text
3DGS iterations
resolution scale
feature matching settings
bundle adjustment settings
plant segmentation settings
tip candidate threshold
skeletonization settings
reprojection loss weight
model surface loss weight
skeleton endpoint loss weight
temporal prior weight
```

進階設定不得再包含：

```text
ROI
ROI margin
MOG2 history
MOG2 learning rate
光照切換面積
人工植物基部像素
```

---

# 10. 每個 Round 的正式分析流程

每個 Round 依以下順序執行：

```text
1. 建立 Round View Manifest
2. 驗證原始影像與 SHA-256
3. 載入 Analysis Run 內參 Snapshot
4. 依相機與解析度建立 Remap
5. 對每張影像執行 Fisheye 去畸變
6. 建立 Valid Pixel Mask
7. 在去畸變影像中偵測 ArUco
8. 估算每張影像的世界座標姿態
9. 計算 ArUco 重投影誤差
10. 執行影像清晰度、曝光與靜態性檢查
11. 選擇 Top 與 Side 代表影像
12. 保留全部有效且不重複的 Rotating 視角
13. 執行多視角特徵提取與匹配
14. 執行受 ArUco 約束的相機姿態精修
15. 建立稀疏三維初始化點
16. 建立每 Round 的 3D Gaussian Splatting 模型
17. 匯出 Gaussian Centers 與 Point Cloud
18. 隔離植物模型並移除背景
19. 建立植物骨架與三維幾何端點候選
20. 在每張去畸變影像中建立二維尖端候選
21. 執行多視角尖端候選匹配
22. 三角化初始三維尖端標記
23. 使用模型表面與骨架精修尖端標記
24. 計算尖端標記信心與品質
25. 保存 Round Model 與 Tip Marker
```

不同 Round 彼此獨立建立模型。

跨 Round 資料只用於：

- 尖端身份串接
- 弱時序先驗
- 異常跳點檢查
- 生長與運動分析
- 模型間比較

不得用於前後像素相減。

---

# 11. 三維模型建立技術棧

## 11.1 技術選擇原則

模型建立不得只寫成抽象的：

```text
執行 3DGS
```

必須指定可實際安裝、執行、測試與替換的技術實作。

系統應將模型建立封裝為獨立 Reconstruction Backend，使 Phyto-Autoscopy 不與單一 3DGS repository 的內部檔案結構永久耦合。

正式介面：

```python
from pathlib import Path
from typing import Protocol


class ReconstructionBackend(Protocol):
    name: str
    version: str

    def check_availability(self) -> dict:
        ...

    def prepare_dataset(
        self,
        round_manifest: "RoundManifest",
        camera_intrinsics: dict,
        camera_poses: list,
        output_dir: Path,
    ) -> "PreparedDataset":
        ...

    def train(
        self,
        dataset: "PreparedDataset",
        parameters: "ReconstructionParameters",
        output_dir: Path,
    ) -> "ReconstructionResult":
        ...

    def export_gaussians(
        self,
        result: "ReconstructionResult",
        output_path: Path,
    ) -> Path:
        ...

    def export_point_cloud(
        self,
        result: "ReconstructionResult",
        output_path: Path,
    ) -> Path:
        ...

    def render_views(
        self,
        result: "ReconstructionResult",
        cameras: list,
        output_dir: Path,
    ) -> list[Path]:
        ...

    def cancel(self) -> None:
        ...
```

第一版至少支援一個正式 Backend，並保留第二個可替換 Backend 的介面。

---

## 11.2 第一版正式 Backend：gsplat

Repository：

```text
https://github.com/nerfstudio-project/gsplat
```

安裝方式：

```bash
pip install gsplat
```

或：

```bash
pip install git+https://github.com/nerfstudio-project/gsplat.git
```

Backend 名稱：

```text
gsplat_3dgs
```

角色：

```text
Primary Reconstruction Backend
```

選擇理由：

- 具有 Python bindings
- 可直接與現有 Python backend 整合
- 使用 CUDA Gaussian rasterization
- 可取得與修改 Gaussian parameters
- 容易加入植物遮罩
- 容易加入世界座標限制
- 容易輸出 Gaussian center、scale、rotation、opacity 與 feature
- 可回報每個 Round 的訓練進度
- 可保存中間 checkpoint
- 可在後續研究中加入尖端標記相關 loss
- 使用 Apache License 2.0

第一版正式模型建立流程應以 `gsplat` 為核心，不要求使用者同時安裝 Graphdeco 官方實作。

---

## 11.3 研究基準 Backend：Graphdeco 官方 3DGS

Repository：

```text
https://github.com/graphdeco-inria/gaussian-splatting
```

Backend 名稱：

```text
graphdeco_3dgs
```

角色：

```text
Reference Reconstruction Backend
```

用途：

- 驗證模型品質
- 建立研究基準
- 重現原始 3DGS 訓練方法
- 對照 `gsplat` backend 的輸出
- 確認自訂流程未偏離原始方法

基本訓練命令：

```bash
python train.py \
  -s <prepared_dataset_path> \
  -m <round_model_output_path>
```

官方實作接受 COLMAP 或 NeRF Synthetic 類型資料。

Phyto-Autoscopy 必須自行建立 dataset adapter，不得讓官方轉換腳本重新從原始畸變影像估算另一套相機座標。

建議資料：

```text
round_dataset/
├─ images/
├─ sparse/
│  └─ 0/
│     ├─ cameras.bin
│     ├─ images.bin
│     └─ points3D.bin
└─ phyto_metadata.json
```

其中：

- `images/` 使用去畸變影像
- `cameras.bin` 使用去畸變後內參
- `images.bin` 使用 ArUco 與姿態精修後外參
- `points3D.bin` 使用稀疏初始化點
- `phyto_metadata.json` 保存 Round 與公制世界座標資訊

### 授權限制

Graphdeco 官方實作主要供研究與評估使用，並限制未經授權的商業用途。

因此：

- 可作為研究型 Phyto-Autoscopy 的參考 Backend
- 不得假定可直接用於商業部署
- 每個 Analysis Run 必須保存使用的 repository、commit 與 license
- 若未來商業化，必須重新審查授權或替換 Backend

---

## 11.4 COLMAP／PyCOLMAP

Repository：

```text
https://github.com/colmap/colmap
```

Python bindings：

```text
pycolmap
```

安裝方式可依環境選擇：

```bash
conda install -c conda-forge colmap
```

或：

```bash
pip install pycolmap
```

在本系統中的用途：

- 特徵提取
- 特徵匹配
- 稀疏三維點建立
- 幾何一致性檢查
- Bundle Adjustment
- 3DGS 稀疏點初始化
- Graphdeco Backend 的 COLMAP dataset 輸出

正式流程：

```text
去畸變影像
＋ ArUco 初始姿態
＋ 公制世界座標
→ PyCOLMAP 特徵與匹配
→ 受約束的姿態精修
→ 稀疏點雲
→ 3DGS 初始化
```

COLMAP 不負責建立世界原點與毫米尺度。

ArUco 世界座標與尺度必須保持固定。

不得讓 COLMAP 產生任意方向與任意尺度的最終座標後覆蓋 ArUco 世界座標。

---

## 11.5 Open3D

Repository：

```text
https://github.com/isl-org/Open3D
```

安裝：

```bash
pip install open3d
```

用途：

- Gaussian center 轉換為點雲
- PLY 讀寫
- 點雲離群值移除
- Voxel downsampling
- 空間裁切
- 平台與背景幾何排除
- 點雲配準
- 法向量估算
- 跨 Round 模型對齊檢查
- 點雲與尖端標記視覺化
- 人工檢查模型顯示

Open3D 不負責主要 3DGS 訓練。

---

## 11.6 OpenCV

使用：

```text
opencv-contrib-python
```

必須包含 ArUco 模組。

用途：

- Fisheye 內參套用
- 去畸變
- ArUco 偵測
- solvePnP
- 重投影
- 二維影像處理
- 植物遮罩前後處理
- 尖端候選診斷
- Overlay 輸出

OpenCV 不負責最終 3DGS 模型訓練。

---

## 11.7 PyTorch

PyTorch 用於：

- `gsplat` 執行基礎
- 3DGS 訓練
- 植物遮罩模型
- 二維尖端候選模型
- 聯合尖端標記最佳化
- GPU 張量處理
- Checkpoint 管理

系統啟動時應檢查：

```text
PyTorch version
CUDA runtime version
CUDA toolkit version
GPU availability
CUDA extension availability
```

不得等到模型訓練開始後才回報 CUDA extension 無法載入。

---

## 11.8 植物分割候選技術

第一版可以先使用傳統與模型式方法並存：

### 傳統方法

```text
OpenCV
→ HSV / Lab 顏色特徵
→ Excess Green
→ Morphology
→ Connected Components
```

### 模型式方法

可選：

```text
Segment Anything Model
https://github.com/facebookresearch/segment-anything
```

或：

```text
MobileSAM
https://github.com/ChaoningZhang/MobileSAM
```

植物分割 Backend 必須獨立封裝，不得讓 3DGS 核心直接依賴單一分割模型。

第一版可先採：

```text
傳統植物顏色遮罩
＋空間世界範圍
＋重建後群聚
```

之後再加入語意分割模型。

---

## 11.9 骨架與幾何處理候選技術

可使用：

```text
Open3D
NumPy
SciPy
scikit-image
NetworkX
```

用途：

- 點雲轉 voxel
- 三維骨架化
- 骨架圖建立
- 分支與端點尋找
- 主生長軸追蹤
- 最短路徑或主幹路徑分析

骨架化方法必須封裝為：

```python
class PlantSkeletonBackend(Protocol):
    def extract(
        self,
        point_cloud_path: Path,
        plant_base_world_mm: tuple[float, float, float],
    ) -> "PlantSkeletonResult":
        ...
```

不得將單一實驗性骨架化函式直接寫死於 `AnalysisService`。

---

## 11.10 第一版正式技術組合

第一版採用：

```text
OpenCV
→ 內參、去畸變、ArUco、PnP、影像遮罩

PyCOLMAP
→ 多視角特徵、稀疏點、姿態精修

gsplat
→ 每 Round 3D Gaussian Splatting 訓練

Open3D
→ 點雲處理、模型清理、配準與檢視

PyTorch
→ GPU 訓練、植物分割與尖端標記最佳化

NumPy / SciPy / NetworkX
→ 數值運算、骨架圖與軌跡分析
```

Graphdeco 官方實作作為：

```text
Reference Backend
```

不作為第一版唯一硬依賴。

---

# 12. Reconstruction Backend 設定

設定檔新增：

```json
{
  "reconstruction": {
    "backend": "gsplat_3dgs",
    "available_backends": [
      "gsplat_3dgs",
      "graphdeco_3dgs"
    ],
    "device": "cuda",
    "fallback_device": null,
    "quality_preset": "standard",
    "save_checkpoint": true,
    "export_gaussians": true,
    "export_point_cloud": true,
    "export_plant_point_cloud": true,
    "export_render_preview": true,
    "use_pose_refinement": true,
    "use_plant_mask": true
  }
}
```

每個 Backend 自行維護：

```text
backend_name
backend_version
repository_url
repository_commit
license
python_version
pytorch_version
cuda_runtime_version
cuda_toolkit_version
gpu_name
gpu_memory
training_parameters
```

上述資料必須固化於每個 Analysis Run。

---

# 13. Backend 執行隔離

3DGS 訓練不得直接阻塞 FastAPI request thread。

模型建立應由：

```text
AnalysisJobManager
→ Reconstruction Worker
→ Reconstruction Backend Adapter
```

執行。

第一版可使用獨立 subprocess：

```text
FastAPI Process
→ 建立 Reconstruction Job
→ 啟動獨立 Python Process
→ 寫入進度
→ 定期回報
→ 保存 Checkpoint
→ 回傳 Model Artifact
```

未來可以替換為：

- Local worker process
- GPU job queue
- Celery
- RQ
- Remote reconstruction node

但 Analysis API、Repository 與 Artifact 格式不得依賴特定執行方式。

## 13.1 取消

取消分析時必須：

- 通知 Reconstruction Worker
- 停止目前訓練
- 保存最後有效 checkpoint
- 不刪除已完成 Round
- 將尚未完成 Round 標記為 cancelled
- 保存取消時間與操作者

## 13.2 錯誤隔離

單一 Round 模型建立失敗時：

- 保存該 Round 錯誤
- 不得刪除其他已完成 Round
- 可依設定繼續後續 Round
- 最終 Analysis Run 可標記為部分完成
- 人工檢查頁應顯示失敗 Round

---

# 14. Backend 可用性檢查

建立分析前檢查：

```text
Python package available
CUDA available
GPU visible
GPU memory available
CUDA extension loadable
selected backend available
COLMAP / PyCOLMAP available
Open3D available
write permission valid
temporary storage sufficient
```

前端顯示：

```text
模型後端：gsplat
狀態：可用
GPU：NVIDIA ...
可用顯示記憶體：... GB
品質模式：標準
PyCOLMAP：可用
Open3D：可用
```

錯誤訊息使用中文，例如：

```text
目前沒有可用的三維模型建立後端。
gsplat 的 CUDA 擴充套件載入失敗。
目前 GPU 記憶體不足以使用高品質模式。
尚未安裝 PyCOLMAP，無法建立稀疏初始化點。
Open3D 無法載入，無法輸出植物點雲。
```

不得直接顯示未翻譯的：

```text
backend unavailable
CUDA extension error
Landmark failed
```

---

# 15. 多視角三維模型

## 15.1 正式模型來源

每個 Round 的模型使用：

```text
全部有效 rotating views
＋ top representative view
＋ side representative view
```

三者從一開始共同參與：

- 姿態精修
- 稀疏幾何建立
- Gaussian 模型訓練
- 模型品質驗證

不得採用：

```text
先用 rotating 建模
→ 最後再把 top / side 當作補點
```

也不得採用：

```text
先用 top / side 三角化一個尖端
→ rotating 只在投影附近搜尋
```

## 15.2 每 Round 獨立模型

正式原則：

```text
one Round
=
one static multi-view scene
=
one independent 3D model
```

每個 Round 產生獨立模型。

不同 Round 不共享同一組 Gaussian 參數。

後續若要研究時變 Gaussian 或模型延續訓練，應另立新 GOAL，不得在第一版中隱式混入。

## 15.3 公制尺度

模型必須使用 ArUco 世界座標與毫米尺度。

不得輸出只有任意尺度的模型。

所有 Round 模型必須共享：

- 世界原點
- 世界軸方向
- 毫米單位
- 平台基準
- 植物中心基準

如此才能直接進行跨 Round 比較。

## 15.4 模型輸出

每個 Round 至少保存：

```text
model_backend
model_backend_version
source_view_ids
camera_intrinsics
camera_poses
Gaussian model path
Gaussian count
training iterations
training duration
training loss summary
render preview paths
point cloud path
plant point cloud path
skeleton path
quality status
failure reason
```

## 15.5 背景處理

重建階段可以保留部分背景特徵，以改善：

- 特徵匹配
- 姿態精修
- 稀疏點初始化
- 模型穩定度

模型建立後，再使用以下資訊移除背景：

- 平台世界邊界
- 植物有效高度範圍
- 空間群聚
- 植物語意遮罩
- Gaussian density
- Gaussian opacity
- 與植物主群聚的連通性

不得只使用 RGB 綠色閾值刪除所有非綠色結構，避免：

- 細莖遺失
- 枯葉遺失
- 低飽和植物區域遺失
- 逆光植物區域遺失

## 15.6 原始模型與植物模型

每個 Round 應區分：

```text
完整場景模型
純植物模型
```

完整場景模型保留：

- 平台
- 背景
- Marker
- 植物

純植物模型只保留植物。

背景移除不得直接覆蓋完整場景模型。

---

# 16. 尖端標記

## 16.1 每 Round 必須輸出

每個成功分析的 Round 必須輸出：

```text
三維尖端標記
```

至少包含：

```text
analysis_id
record_id
mode_id
round_id
timestamp
x_mm
y_mm
z_mm
confidence
valid
source
supporting_view_ids
visible_view_count
mean_reprojection_error_px
maximum_reprojection_error_px
distance_to_model_mm
distance_to_skeleton_mm
temporal_distance_mm
manually_corrected
failure_reason
```

## 16.2 尖端標記不得等同模型最高點

不得直接使用：

```text
maximum Z
最高 Gaussian
最高 point
離平台最遠 point
```

作為正式尖端標記。

原因包括：

- 主莖尖端可能水平彎曲
- 葉尖可能高於主莖尖端
- 支架可能高於植物
- 模型可能存在漂浮 Gaussian
- 細莖末端可能重建不完整
- 植物可能具有多個幾何端點

## 16.3 二維尖端候選

每張去畸變影像可建立：

```text
plant mask
tip candidate heatmap
tip candidate points
candidate confidence
visibility confidence
```

第一版可以結合：

- 單張植物分割
- 主莖或主軸分割
- 二維骨架端點
- 幾何曲線端點
- 尖端關鍵點模型
- 多視角重投影一致性

不得依賴：

- 人工 ROI
- 不同 Round 的像素差
- 單純最高像素
- 單純離基部最遠像素

## 16.4 Top 與 Side 的角色

top 與 side 為固定相機，適合提供穩定尖端證據：

```text
top
→ 穩定的 XY 平面觀測

side
→ 穩定的高度與側向觀測

top + side
→ 初始三維尖端候選
```

但完整多視角模式不得只以 top 與 side 決定最終尖端標記。

旋臂多視角應共同參與：

- 候選確認
- 遮擋補足
- 三角化
- 重投影誤差
- 最終精修

## 16.5 三維初始尖端

由多個相機中的二維候選建立三維候選：

```text
2D tip candidates
＋ camera intrinsics
＋ camera poses
→ robust multi-view triangulation
→ initial 3D tip marker
```

三角化必須：

- 至少有兩個有效視角
- 優先選擇基線與方向差異足夠的觀測
- 使用 RANSAC 或穩健損失排除離群候選
- 計算各支持視角重投影誤差
- 保存被排除候選與原因

## 16.6 模型端尖端候選

3DGS 完成後：

```text
Gaussian centers
→ plant isolation
→ point cloud cleanup
→ skeletonization
→ geometric endpoint candidates
```

模型端候選至少保存：

```text
endpoint_position_mm
branch_id
local_radius_mm
local_density
distance_from_plant_base_mm
supporting_point_count
supporting_gaussian_count
```

## 16.7 主生長軸

模型骨架中可能同時存在：

- 主莖端點
- 葉片端點
- 側枝端點
- 雜訊端點

系統必須建立主生長軸辨識邏輯。

可使用：

- 與植物基部的骨架連通性
- 主路徑長度
- 局部半徑
- 方向連續性
- 過去 Round 的主軸
- 多視角二維尖端證據

不得把所有幾何端點視為同等候選。

## 16.8 聯合精修

最終尖端標記由以下證據共同決定：

```text
多視角二維尖端重投影
＋三維植物表面
＋植物骨架端點
＋主生長軸連通性
＋上一 Round 尖端標記弱先驗
```

可定義聯合成本：

```text
tip_loss =
    reprojection_loss
  + model_surface_loss
  + skeleton_endpoint_loss
  + main_axis_loss
  + temporal_continuity_loss
  + visibility_loss
```

上一 Round 只能作為弱先驗。

若植物真實移動幅度較大，時序先驗不得強迫尖端留在舊位置。

## 16.9 尖端標記信心

信心至少依以下資料計算：

- 有效支持視角數
- 支持視角的角度分布
- 平均重投影誤差
- 最大重投影誤差
- 與模型表面的距離
- 與骨架端點的距離
- 模型局部密度
- 與主生長軸的連通性
- 與上一 Round 的合理位移
- ArUco 姿態品質
- Round 模型品質
- 尖端是否被遮擋

信心不得只是固定常數或單一門檻。

## 16.10 尖端標記來源

正式來源值可包含：

```text
multiview_joint
top_side_triangulation
model_skeleton
temporal_estimate
manual
invalid
```

前端顯示映射：

```text
multiview_joint
→ 多視角聯合分析

top_side_triangulation
→ 俯視與側視三角化

model_skeleton
→ 模型骨架推定

temporal_estimate
→ 時序估計

manual
→ 人工修正

invalid
→ 無效
```

---

# 17. 跨 Round 尖端標記軌跡

## 17.1 軌跡建立

完成各 Round 尖端標記後，依：

```text
mode_id
round order
timestamp
```

建立：

```text
Tip Marker Trajectory
```

使用者可見名稱：

```text
尖端標記軌跡
```

每一點至少包含：

```text
round_id
timestamp
x_mm
y_mm
z_mm
confidence
valid
detection_type
```

## 17.2 可分析資料

正式輸出至少支援計算：

- 三維位移
- 相鄰 Round 距離
- 速度
- 加速度
- 運動方向
- 水平位移
- 垂直生長量
- 路徑長度
- 曲率
- 旋轉方向
- Nutation 半徑
- Nutation 週期
- 向支架接近距離
- 缺失區段
- 有效量測比例

## 17.3 原始點與衍生點

軌跡點必須區分：

```text
measured
estimated
interpolated
manual
invalid
```

前端顯示：

```text
measured
→ 實際量測

estimated
→ 模型估計

interpolated
→ 插值

manual
→ 人工修正

invalid
→ 無效
```

## 17.4 插值

不得預設自動填補所有缺失尖端標記。

插值只能發生於：

- 缺口長度在允許範圍內
- 前後點信心足夠
- 移動速度合理
- 中間 Round 沒有重大模型失敗
- 沒有相機或平台重新定位事件
- 不跨越不同 mode
- 不跨越 Record 中斷

原始量測點與插值點必須清楚區分。

---

# 18. 人工檢查與修正

## 18.1 新人工檢查目標

人工檢查不再只處理 top 與 side 的二維點。

應可檢查：

- 每 Round 三維模型
- 三維尖端標記
- top 二維重投影
- side 二維重投影
- rotating 二維重投影
- 支持候選
- 排除候選
- 尖端標記信心
- 相機姿態品質
- 模型品質
- 骨架與主生長軸

## 18.2 二維修正

操作人員可在至少兩個影像視角中重新指定尖端。

系統重新執行：

```text
multi-view triangulation
→ model-constrained refinement
→ tip marker quality calculation
```

## 18.3 三維修正

若提供直接三維修正，必須：

- 顯示植物模型
- 顯示原尖端標記
- 顯示修正尖端標記
- 顯示所有視角重投影
- 顯示與模型和骨架距離
- 保存修正者
- 保存修正時間
- 保存修正原因
- 不覆蓋原自動結果

## 18.4 修正歷史

每次修正保存：

```text
automatic_tip
corrected_tip
operator_id
created_at
reason
supporting_views
reprojection_before
reprojection_after
confidence_before
confidence_after
```

## 18.5 無效標記

操作人員可將某個 Round 標記為：

```text
尖端不可確認
```

此操作不得強迫輸入座標。

系統保存：

```text
valid = false
failure_reason = manual_invalid
```

---

# 19. 新第 4 步「確認並建立」

## 19.1 移除舊摘要

移除：

- 起始影格
- 結束影格
- 人工影格偏移
- 俯視 ROI
- 側視 ROI
- MOG2 參數摘要
- 動態 ROI 摘要
- 舊式環繞精修描述

## 19.2 Record 與模式摘要

顯示：

```text
Record ID
Record 根目錄
選取模式
模式數量
Round 數量
有效 Round 數量
不完整 Round 數量
總影像數
```

## 19.3 相機與內參摘要

每台相機顯示：

```text
相機
是否啟用
影像數
解析度
內參是否存在
內參是否有效
相機模型
內參重投影誤差
內參版本
```

若任何已啟用相機缺少有效內參：

```text
禁止建立分析
```

## 19.4 ArUco 摘要

顯示：

```text
佈局版本
Dictionary
Marker 數量
Marker 尺寸
世界原點
世界單位
抽樣偵測狀態
```

若 ArUco Layout 不完整：

```text
禁止建立分析
```

## 19.5 多視角覆蓋摘要

每個選取模式顯示：

```text
Round 數量
平均 Rotating 視角數
最少 Rotating 視角數
角度覆蓋率
Top 可用率
Side 可用率
ArUco 可見率
平均 Round 捕捉時間
```

## 19.6 模型後端摘要

顯示：

```text
模型後端
後端版本
GPU
可用 GPU 記憶體
PyTorch
CUDA
PyCOLMAP
Open3D
品質模式
預估輸出
```

## 19.7 方法摘要

顯示：

```text
分析方法
模型建立方法
模型品質
相機姿態方法
是否執行姿態精修
背景處理方式
是否建立完整點雲
是否建立純植物點雲
是否建立骨架
是否建立尖端標記
是否等待人工確認
```

## 19.8 預期輸出

顯示：

```text
每 Round Gaussian 模型
每 Round 完整點雲
每 Round 純植物點雲
每 Round 植物骨架
每 Round 三維尖端標記
跨 Round 尖端標記軌跡
模型與標記品質報告
輸出根目錄
```

## 19.9 建立前預檢

建立 Analysis Run 前必須執行：

```text
validate Record
→ validate selected modes
→ group Round views
→ validate image files
→ validate image hashes
→ validate resolutions
→ validate intrinsics
→ validate ArUco layout
→ sample ArUco detection
→ inspect rotating angular coverage
→ inspect Round duration
→ check reconstruction backend
→ check CUDA and GPU memory
→ calculate expected Round count
→ return readiness
```

## 19.10 Error

以下會阻止建立：

- 找不到 Record
- 沒有選取模式
- 沒有有效 Round
- 必要相機沒有影像
- 必要相機沒有有效內參
- ArUco Layout 不完整
- 影像解析度與內參不相容
- 無法建立任何有效多視角 Round
- 模型後端不可用
- CUDA Backend 無法載入
- 儲存空間不足
- 輸出目錄不可寫入

## 19.11 Warning

以下允許建立但需顯示：

- 部分 Round 缺少角度
- 部分影像看不到足夠 ArUco
- Round 捕捉時間過長
- 部分影像模糊
- 部分固定相機姿態偏移
- 部分 Round 只能建立低品質模型
- GPU 記憶體不足以使用高品質模式
- 部分 Round 可能只能產生尖端標記而無法建立完整模型

---

# 20. 資料模型重構

## 20.1 AnalysisRun

目前已有以下欄位應保留並正式使用：

```text
intrinsics_snapshot
aruco_layout_snapshot
camera_pose_results
pose_estimation_version
pose_quality
```

建議新增：

```text
reconstruction_backend
reconstruction_backend_version
reconstruction_environment
round_count
completed_round_count
failed_round_count
tip_marker_count
trajectory_status
```

## 20.2 AnalysisCreateRequest

移除：

```text
start_frame
end_frame
top_roi
side_roi
manual_frame_offset
```

建議：

```python
class AnalysisCreateRequest(BaseModel):
    record_id: str
    mode_ids: list[str]
    method: AnalysisMethod
    camera_sources: dict[CameraIdentifier, AnalysisCameraSource]
    parameters: dict[str, Any]
    manual_review_required: bool = True
```

## 20.3 AnalysisMethod

建議：

```python
AnalysisMethod = Literal[
    "round_multiview",
    "top_side_tip_only",
]
```

舊方法值可保留於舊 Run 相容層：

```text
top_side
top_side_rotating
```

但新 Analysis Run 不再建立為舊方法。

## 20.4 AnalysisRound

新增：

```python
class AnalysisRound(BaseModel):
    analysis_id: str
    round_key: str
    record_id: str
    mode_id: str
    round_id: str
    started_at: str | None = None
    ended_at: str | None = None
    duration_seconds: float | None = None
    status: str
    view_count: int
    top_view_count: int
    side_view_count: int
    rotating_view_count: int
    angular_coverage_deg: float | None = None
    static_scene_score: float | None = None
    model_result_id: str | None = None
    tip_landmark_id: str | None = None
    failure_reason: str | None = None
```

內部可以使用：

```text
tip_landmark_id
```

使用者可見顯示為：

```text
尖端標記 ID
```

## 20.5 AnalysisView

新增：

```python
class AnalysisView(BaseModel):
    analysis_id: str
    round_key: str
    view_id: str
    capture_id: int
    camera_id: CameraIdentifier
    snapshot_id: str | None = None
    timestamp: str
    relative_path: str
    angle_deg: float | None = None
    motor_position_deg: float | None = None
    image_width: int
    image_height: int
    image_sha256: str
    selected_for_reconstruction: bool
    exclusion_reason: str | None = None
    pose_status: str | None = None
    pose_reprojection_error_px: float | None = None
```

## 20.6 CameraPoseResult

正式化：

```python
class CameraPoseResult(BaseModel):
    analysis_id: str
    round_key: str
    view_id: str
    camera_id: CameraIdentifier
    rotation_matrix: list[list[float]]
    translation_vector_mm: list[float]
    camera_center_world_mm: list[float]
    detected_marker_ids: list[int]
    detected_corner_count: int
    aruco_reprojection_error_px: float | None
    refinement_reprojection_error_px: float | None
    pose_source: str
    valid: bool
    failure_reason: str | None = None
```

## 20.7 RoundModelResult

新增：

```python
class RoundModelResult(BaseModel):
    analysis_id: str
    round_key: str
    model_id: str
    backend: str
    backend_version: str
    status: str
    source_view_ids: list[str]
    model_path: str | None = None
    point_cloud_path: str | None = None
    plant_point_cloud_path: str | None = None
    skeleton_path: str | None = None
    gaussian_count: int | None = None
    point_count: int | None = None
    training_iterations: int | None = None
    training_duration_seconds: float | None = None
    model_quality: dict[str, Any]
    failure_reason: str | None = None
```

## 20.8 TipLandmark

內部類別可保留：

```python
class TipLandmark(BaseModel):
    analysis_id: str
    round_key: str
    tip_id: str
    timestamp: str | None = None
    x_mm: float | None = None
    y_mm: float | None = None
    z_mm: float | None = None
    confidence: float
    valid: bool
    source: str
    supporting_view_ids: list[str]
    visible_view_count: int
    mean_reprojection_error_px: float | None = None
    maximum_reprojection_error_px: float | None = None
    distance_to_model_mm: float | None = None
    distance_to_skeleton_mm: float | None = None
    temporal_distance_mm: float | None = None
    detection_type: str
    manually_corrected: bool
    failure_reason: str | None = None
```

使用者可見名稱一律為：

```text
尖端標記
```

## 20.9 TipObservation2D

新增：

```python
class TipObservation2D(BaseModel):
    analysis_id: str
    round_key: str
    view_id: str
    candidate_id: str
    x_px: float
    y_px: float
    confidence: float
    visibility_confidence: float
    selected: bool
    rejection_reason: str | None = None
```

## 20.10 舊 AnalysisFramePair

目前 `AnalysisFramePair` 只能保存一張 rotating image，不適合作為新多視角模型的主要資料結構。

處理方式：

- 舊 Analysis Run 自正式資料庫移除
- 移除舊 Run 的讀取、操作與匯出介面
- 移除 `AnalysisFramePair` 舊資料表與 API
- 新方法只使用 `AnalysisRound` 與 `AnalysisView`
- 清理前將完整 SQLite 保存至 `phyto_autoscopy-backup.sqlite3`

---

# 21. Analysis Stage 重構

新的 Stage 建議：

```text
validating
grouping_rounds
snapshotting_intrinsics
undistorting_images
detecting_aruco
estimating_camera_poses
refining_camera_poses
selecting_reconstruction_views
extracting_features
matching_features
initializing_round_geometry
detecting_tip_candidates
reconstructing_round_model
isolating_plant_model
extracting_model_point_cloud
extracting_model_skeleton
triangulating_tip_marker
refining_tip_marker
linking_tip_trajectory
waiting_for_review
calculating_quality_metrics
exporting
completed
```

前端中文：

```text
validating
→ 驗證輸入資料

grouping_rounds
→ 整理分析輪次

snapshotting_intrinsics
→ 固化相機內參

undistorting_images
→ 套用內參並去畸變

detecting_aruco
→ 偵測 ArUco 基準

estimating_camera_poses
→ 估算相機姿態

refining_camera_poses
→ 精修相機姿態

selecting_reconstruction_views
→ 選擇模型影像

extracting_features
→ 提取多視角特徵

matching_features
→ 配對多視角特徵

initializing_round_geometry
→ 建立初始三維幾何

detecting_tip_candidates
→ 偵測尖端候選

reconstructing_round_model
→ 建立每輪三維模型

isolating_plant_model
→ 分離植物模型

extracting_model_point_cloud
→ 建立植物點雲

extracting_model_skeleton
→ 建立植物骨架

triangulating_tip_marker
→ 計算三維尖端標記

refining_tip_marker
→ 精修尖端標記

linking_tip_trajectory
→ 建立尖端標記軌跡

waiting_for_review
→ 等待人工確認

calculating_quality_metrics
→ 計算品質指標

exporting
→ 輸出分析結果

completed
→ 已完成
```

前端與後端需同步更新：

```text
ANALYSIS_STAGE_LABELS
AnalysisStage
progress calculation
status display
tests
```

---

# 22. Backend 模組拆分

不得繼續將完整流程塞入：

```text
backend/app/services/analysis_service.py
```

建議新增：

```text
backend/app/analysis/rounds/
  round_grouper.py
  round_validator.py
  view_selector.py
  round_quality.py
  static_scene_validator.py

backend/app/analysis/intrinsics/
  snapshot.py
  resolution_adapter.py
  undistortion.py
  remap_cache.py

backend/app/analysis/pose_alignment/
  aruco_detector.py
  aruco_world.py
  pose_estimator.py
  fixed_camera_pose.py
  rotating_pose.py
  bundle_adjustment.py
  pose_quality.py

backend/app/analysis/reconstruction/
  backend.py
  backend_registry.py
  reconstruction_worker.py
  dataset_adapter.py
  colmap_dataset.py
  sparse_initializer.py
  round_reconstructor.py
  model_export.py
  model_quality.py
  plant_isolation.py

backend/app/analysis/reconstruction/backends/
  gsplat_backend.py
  graphdeco_backend.py

backend/app/analysis/tip/
  candidate_detector.py
  candidate_matcher.py
  triangulation.py
  model_endpoints.py
  skeleton_extractor.py
  main_axis.py
  marker_optimizer.py
  confidence.py
  trajectory_linker.py

backend/app/analysis/review/
  correction_service.py
  reprojection_overlay.py
  model_review.py
```

`AnalysisService` 只負責：

- Run 生命週期
- 輸入驗證
- 背景工作排程
- Stage 與進度
- 呼叫分析模組
- Artifact 管理
- Repository 寫入
- 取消
- 失敗
- 重試
- 錯誤回報

---

# 23. Artifact 結構

每個 Analysis Run 建議使用：

```text
analysis_<id>/
├─ run.json
├─ parameters.json
├─ input_manifest.json
├─ intrinsics_snapshot.json
├─ aruco_layout_snapshot.json
├─ reconstruction_environment.json
├─ round_index.json
├─ logs/
│  ├─ analysis.log.csv
│  └─ reconstruction.log.csv
├─ rounds/
│  ├─ <round_key>/
│  │  ├─ round.json
│  │  ├─ views.json
│  │  ├─ camera_poses.json
│  │  ├─ quality.json
│  │  ├─ undistortion/
│  │  │  ├─ metadata.json
│  │  │  └─ valid_masks/
│  │  ├─ sparse/
│  │  │  ├─ cameras.bin
│  │  │  ├─ images.bin
│  │  │  └─ points3D.bin
│  │  ├─ tip/
│  │  │  ├─ candidates_2d.json
│  │  │  ├─ candidates_3d.json
│  │  │  ├─ tip_marker.json
│  │  │  ├─ marker_quality.json
│  │  │  └─ reprojection.json
│  │  ├─ model/
│  │  │  ├─ gaussians.ply
│  │  │  ├─ scene_point_cloud.ply
│  │  │  ├─ plant_point_cloud.ply
│  │  │  ├─ skeleton.json
│  │  │  ├─ model_metadata.json
│  │  │  └─ checkpoint/
│  │  ├─ masks/
│  │  ├─ renders/
│  │  └─ overlays/
├─ trajectory/
│  ├─ tip_marker_trajectory.csv
│  ├─ tip_marker_trajectory.json
│  └─ trajectory_quality.json
└─ summaries/
   ├─ round_summary.csv
   ├─ model_quality.json
   ├─ tip_marker_quality.json
   └─ analysis_summary.json
```

大型去畸變影像可依設定決定是否永久保存。

即使不保存影像，也必須保存：

- Remap metadata
- 原始影像 SHA-256
- 內參 Snapshot
- 處理版本
- 相機姿態
- 模型來源影像
- 失敗原因

---

# 24. CSV 輸出

## 24.1 尖端標記軌跡

```csv
record_id,mode_id,round_id,timestamp,x_mm,y_mm,z_mm,confidence,valid,detection_type,visible_view_count,mean_reprojection_error_px,manually_corrected
```

## 24.2 Round 摘要

```csv
record_id,mode_id,round_id,status,view_count,top_view_count,side_view_count,rotating_view_count,angular_coverage_deg,duration_seconds,model_status,tip_marker_status
```

## 24.3 使用者可見欄名

下載介面顯示中文欄位說明：

```text
尖端標記 X
尖端標記 Y
尖端標記 Z
標記信心
有效狀態
標記來源
支持視角數
平均重投影誤差
是否人工修正
```

原始 CSV 可保留穩定英文 machine-readable header。

---

# 25. 前端修改範圍

## 25.1 `analysisConfig.js`

修改：

```text
ANALYSIS_SETUP_STEPS
ANALYSIS_METHODS
ANALYSIS_STAGE_LABELS
ANALYSIS_PARAMETER_DEFAULTS
```

新的步驟：

```javascript
export const ANALYSIS_SETUP_STEPS = [
  {
    id: 1,
    label: "選擇紀錄",
  },
  {
    id: 2,
    label: "配置設定",
  },
  {
    id: 3,
    label: "重建與尖端分析",
  },
  {
    id: 4,
    label: "確認並建立",
  },
];
```

刪除：

```text
MOG2_PARAMETER_FIELDS
LIGHTING_PARAMETER_FIELDS
TOP_DETECTION_PARAMETER_FIELDS
SIDE_DETECTION_PARAMETER_FIELDS
MINIMUM_PATH_CONNECTIVITY_OPTIONS
ROI defaults
plant base defaults
```

新增：

```text
RECONSTRUCTION_QUALITY_OPTIONS
POSE_REFINEMENT_OPTIONS
BACKGROUND_PROCESSING_OPTIONS
TIP_ANALYSIS_DEFAULTS
OUTPUT_OPTIONS
```

## 25.2 `AnalysisNew.js`

刪除：

```text
AnalysisSetupRangeStep
updateRoi
currentStep === 3 的 Range branch
```

重排：

```text
1 → AnalysisAvailableRecords
2 → AnalysisSetupSourcesStep
3 → AnalysisSetupReconstructionStep
4 → AnalysisSetupSummaryStep
```

## 25.3 新增元件

建議：

```text
AnalysisSetupReconstructionStep.js
AnalysisReconstructionBackendPanel.js
AnalysisReconstructionQualityPanel.js
AnalysisPoseStrategyPanel.js
AnalysisBackgroundStrategyPanel.js
AnalysisTipMarkerSettingsPanel.js
AnalysisOutputSettingsPanel.js
AnalysisRoundReadinessSummary.js
AnalysisBackendReadinessSummary.js
```

使用者可見元件名稱中使用：

```text
TipMarker
```

前端顯示文字使用：

```text
尖端標記
```

## 25.4 `analysisUtils.js`

刪除：

```text
parseRoi
validateRoiBounds
analysisFrameCount
startFrame validation
endFrame validation
manualFrameOffset validation
ROI payload
old segmentation payload
old top detection payload
old side detection payload
```

新增：

```text
buildReconstructionParameters
normalizeRoundReadiness
normalizeBackendReadiness
validateIntrinsicsReadiness
validateArUcoReadiness
validateReconstructionSetup
buildAnalysisCreatePayload
```

## 25.5 `AnalysisSetupSummaryStep.js`

移除：

- 分析影格
- 人工影格偏移
- 俯視 ROI
- 側視 ROI
- 舊分析方法名稱

新增：

- Round readiness
- 每台相機內參狀態
- ArUco Layout
- 多視角覆蓋
- 模型 Backend
- GPU 與 CUDA 狀態
- 3DGS 設定
- 尖端標記設定
- 預期輸出

---

# 26. Backend 修改範圍

主要修改：

```text
backend/app/models/analysis_models.py
backend/app/core/config.py
backend/config/analysis.json
backend/app/services/analysis_service.py
backend/app/repositories/analysis_repository.py
backend/app/analysis/artifacts.py
backend/app/analysis/record_validator.py
backend/app/analysis/source_validator.py
backend/app/analysis/frame_pairing.py
```

完整多視角方法不再依賴以下舊核心：

```text
mog2_background.py
ROI-based top_tip_detection
ROI-based side_tip_detection
dynamic ROI update
manual frame offset
single rotating frame pairing
detect_rotating_tip_near_projection 作為主要方法
```

舊模組可暫時保留供：

- 舊 Analysis Run
- `top_side_tip_only`
- 回歸測試
- 方法比較

但不得繼續成為 `round_multiview` 的執行核心。

---

# 27. Repository 與 Migration

新增資料表建議：

```text
analysis_rounds
analysis_views
analysis_camera_poses
analysis_round_models
analysis_tip_landmarks
analysis_tip_observations
analysis_tip_corrections
analysis_trajectory_points
```

建議索引：

```text
UNIQUE(analysis_id, round_key)
UNIQUE(analysis_id, view_id)
UNIQUE(analysis_id, round_key, camera_id, capture_id)
UNIQUE(analysis_id, round_key, tip_id)
INDEX(analysis_id, status)
INDEX(analysis_id, mode_id, round_id)
```

舊 Analysis Run 與其專用資料表在完成 SQLite 備份後自正式資料庫移除。

Migration 必須：

- 可重複執行
- 支援空資料庫
- 支援既有資料庫
- 清理前建立 `phyto_autoscopy-backup.sqlite3`
- 不覆蓋新方法 artifacts

---

# 28. 測試

## 28.1 前端測試

必須驗證：

- 新增分析只有四步
- 原第 3 步完全不存在
- 沒有起始影格
- 沒有結束影格
- 沒有人工影格偏移
- 沒有任何 ROI 欄位
- 沒有 ROI 摘要
- 沒有人工植物基部像素
- 新第 3 步顯示模型與尖端標記設定
- 新第 4 步顯示 Round、內參與 ArUco readiness
- 顯示模型 Backend readiness
- Error 會阻止建立
- Warning 不會被誤當成 Error
- Payload 不含舊欄位
- 所有使用者可見 Landmark 已改為「標記」

## 28.2 內參測試

必須驗證：

- top 使用 top intrinsics
- side 使用 side intrinsics
- 所有 rotating views 使用 rotating intrinsics
- 不同旋臂角度不建立不同內參
- Fisheye 使用正確 OpenCV API
- 相同解析度重用 Remap Cache
- 解析度不相容時阻止分析
- 後續座標全部為 undistorted coordinate space
- Analysis Run 固化內參 Snapshot
- 更新正式內參不改變舊 Run

## 28.3 Round 分組測試

必須驗證：

- 依 Record、Mode、Round 正確分組
- 同一 Round 保留全部 rotating views
- 不再只選一張 rotating image
- 不同模式的相同 Round number 不會混合
- 缺少部分角度可標記為不完整
- `round.00` 可正確識別
- 重複角度可選出品質較佳影像
- top／side 重複姿態不會被過度加入模型
- Round 捕捉時間正確計算

## 28.4 ArUco 與姿態測試

必須驗證：

- ArUco 在去畸變影像上偵測
- Pose 使用去畸變相機矩陣
- top／side 可建立穩健固定姿態
- rotating 每張影像有獨立姿態
- motor angle 不是最終外參
- Pose refinement 不改變世界尺度
- ArUco 不足時保存失敗原因
- 固定相機位移可以被發現
- 補足姿態的來源可追溯

## 28.5 Backend 測試

必須驗證：

- `gsplat_3dgs` 可用性檢查
- CUDA 不可用時回傳明確錯誤
- GPU 記憶體不足時降低品質或阻止
- Worker 不阻塞 FastAPI request
- 取消訓練可保存 checkpoint
- 單 Round 失敗不刪除其他 Round
- Backend metadata 正確保存
- Graphdeco Backend 授權資訊正確保存

## 28.6 模型測試

必須驗證：

- 每個有效 Round 建立獨立模型
- rotating、top、side 共同參與模型
- 不使用不同 Round 像素相減
- 模型使用毫米世界座標
- 可輸出 Gaussian model
- 可輸出完整點雲
- 可輸出純植物點雲
- 可建立骨架
- 背景移除不破壞完整原始模型
- 失敗 Round 不影響其他 Round

## 28.7 尖端標記測試

必須驗證：

- 每 Round 可輸出三維尖端標記
- 尖端標記不是直接取 maximum Z
- 二維候選使用去畸變座標
- 多視角三角化可排除離群候選
- 尖端標記靠近植物模型或骨架
- 支持視角數正確
- 重投影誤差正確
- 信心不是固定常數
- 低信心結果可進入人工檢查
- 跨 Round 可建立軌跡
- 缺失點與插值點清楚區分
- 使用者可見文字全部使用「標記」

## 28.8 資料清理測試

必須驗證：

- 清理前可建立完整備份資料庫
- 正式資料庫只保留新版 Analysis Run
- 舊 Run 專用資料表已移除
- 新 Migration 可重複執行
- 新方法不覆蓋既有正式 Artifact
- Reset、Cancel、Retry 對 Round 工作有效
- 程式異常中止後可保留已完成 Round
- 舊 `top_side` 與 `top_side_rotating` Run 不被重新解讀為新方法

---

# 29. 實作順序

## Phase 1 — 移除原第 3 步

1. 將五步改為四步
2. 刪除 `AnalysisSetupRangeStep`
3. 刪除起始與結束影格
4. 刪除人工影格偏移
5. 刪除 ROI
6. 刪除人工植物基部像素
7. 更新前端驗證
8. 更新 Payload
9. 更新後端 Request Schema
10. 修正相關測試

## Phase 2 — Round 與 View 資料模型

1. 新增 `AnalysisRound`
2. 新增 `AnalysisView`
3. 改寫來源掃描
4. 依 Mode／Round／Snapshot 分組
5. 保留全部 Rotating Views
6. 建立資料庫 Migration
7. 建立 Round Readiness
8. 補單元測試

## Phase 3 — 內參與去畸變

1. 固化 Intrinsics Snapshot
2. 建立 Resolution Adaptation
3. 建立 Fisheye Remap Cache
4. 對所有 Analysis View 去畸變
5. 建立 Valid Pixel Mask
6. 統一 Undistorted Coordinate Space
7. 保存處理 Metadata
8. 完成測試

## Phase 4 — ArUco 姿態

1. 固化 ArUco Layout
2. 在去畸變影像偵測 ArUco
3. 建立每張影像 Pose
4. 建立固定相機穩健姿態
5. 建立旋臂逐張姿態
6. 加入馬達弱先驗
7. 加入受約束姿態精修
8. 保存 Pose Quality

## Phase 5 — Reconstruction Backend

1. 建立 `ReconstructionBackend`
2. 建立 Backend Registry
3. 建立 Backend Availability Check
4. 建立 Reconstruction Worker
5. 整合 `gsplat_3dgs`
6. 建立 Graphdeco Reference Adapter
7. 建立 Checkpoint 與 Cancel
8. 保存 Backend Environment

## Phase 6 — PyCOLMAP 初始化

1. 建立去畸變影像 Dataset
2. 寫入已知 Camera Intrinsics
3. 寫入 ArUco 初始 Pose
4. 提取特徵
5. 匹配特徵
6. 建立稀疏點
7. 執行受約束 Bundle Adjustment
8. 輸出 3DGS Dataset

## Phase 7 — Round 3DGS

1. 建立 Reconstruction View Selector
2. 選擇 Top／Side 代表影像
3. 保留全部有效 Rotating Views
4. 建立每 Round 3DGS
5. 匯出 Gaussian Model
6. 匯出 Scene Point Cloud
7. 建立純植物模型
8. 匯出 Plant Point Cloud
9. 建立模型品質摘要

## Phase 8 — 骨架與尖端標記

1. 建立二維尖端候選
2. 建立多視角候選匹配
3. 建立穩健三角化
4. 從模型建立三維骨架
5. 辨識主生長軸
6. 建立模型端端點候選
7. 聯合精修尖端標記
8. 建立信心評分
9. 建立尖端標記 Artifact

## Phase 9 — 跨 Round 軌跡

1. 依 Mode 與時間排序
2. 串接有效尖端標記
3. 標記缺失與離群點
4. 加入有限插值
5. 輸出 CSV／JSON
6. 建立基礎運動指標
7. 建立軌跡品質摘要

## Phase 10 — 新第 3、4 步介面

1. 建立重建與尖端分析頁
2. 建立模型 Backend 狀態
3. 建立 Round Readiness 摘要
4. 建立內參與 ArUco 摘要
5. 建立輸出摘要
6. 建立人工檢查入口
7. 完成前端測試

## Phase 11 — 資料清理與回歸

1. 備份並移除舊 Run
2. 更新 Method Version
3. 更新 Artifact Exporter
4. 執行 Backend 全測試
5. 執行 Frontend 全測試
6. 使用真實多 Round Record 驗證
7. 更新 README
8. 更新架構文件

---

# 30. Method Version

新增：

```text
round_multiview
version: 1.0.0
```

若保留固定雙相機尖端模式：

```text
top_side_tip_only
version: 2.0.0
```

舊方法 `top_side` 與 `top_side_rotating` 已自正式服務移除；歷史資料只保留於獨立備份資料庫。

---

# 31. 完成條件

以下條件全部達成，GOAL-05 才算完成：

- 新增分析由五步正確改為四步
- 原第 3 步「分析範圍」完全移除
- 不再使用 `start_frame`
- 不再使用 `end_frame`
- 不再使用人工 `frame_offset`
- 前後端完全沒有人工 ROI
- 不再要求植物基部像素
- 每個 Analysis Run 固化已啟用相機內參
- 每張影像在所有分析前完成 Fisheye 去畸變
- 所有後續二維座標統一為去畸變座標
- 每張影像使用 ArUco 建立世界座標姿態
- top 與 side 有逐張姿態品質檢查
- rotating 每張影像有獨立姿態
- 同一 Round 的全部有效旋臂視角皆被保留
- 不同 Round 的影像不做前後像素相減
- 一個 Round 建立一個三維植物模型
- top、side、rotating 共同參與模型建立
- 第一版正式支援 `gsplat_3dgs`
- 支援 `graphdeco_3dgs` 作為研究對照 Backend
- 模型 Backend 使用統一介面
- 模型訓練不阻塞 FastAPI Request Thread
- 每個 Round 可輸出 Gaussian Model
- 每個 Round 可輸出完整點雲
- 每個 Round 可輸出純植物點雲
- 每個 Round 可輸出植物骨架
- 每個成功 Round 產生三維尖端標記
- 尖端標記具有毫米座標
- 尖端標記具有信心與品質資料
- 尖端標記不是直接取模型最高點
- 尖端標記由多視角、模型與骨架共同精修
- 各 Round 尖端標記可串接成三維軌跡
- 低信心結果可進行人工檢查
- 所有使用者可見的 `Landmark` 均顯示為「標記」
- 植物尖端一律顯示為「尖端標記」
- 不得將內部英文識別碼直接顯示於 UI
- 每次模型建立保存 Backend、版本、Commit、授權與環境
- 建立分析前可檢查 Backend 與 GPU 是否可用
- Graphdeco Backend 的研究用途授權限制被明確保存
- 模型失敗時保存階段、錯誤與最後 Checkpoint
- 所有輸入、內參、姿態、模型與尖端標記結果可追溯
- 原始 Record 影像保持唯讀
- 舊 Analysis Run 已備份並自正式服務移除
- 前端、後端、整合與相容性測試全部通過


# GOAL-04 - ArUco Automatic Extrinsic Alignment

# Phyto-Autoscopy

### 分析時自動外參對齊與 ArUco 世界座標基準

---

## 1. 目標

移除所有預先建立、保存、切換與啟用外參校正檔的流程。

三顆相機只保留各自唯一的內參。外參不再於「校正」頁面預先求解，而是在每個 Analysis Run 執行時，根據裝置底部四個固定 ArUco 標記自動計算。

外參仍然存在，但改為：

```text
每個資料集自動產生的分析結果
```

而非：

```text
使用者預先管理的校正檔
```

---

## 2. 校正頁面調整

`/calibration` 只保留：

- 三顆相機各自的內參校正
- ChArUco 校正板設定
- 即時相機預覽
- 原始／去畸變預覽
- 內參品質與重投影誤差
- 每顆相機唯一內參的套用與更新

移除：

- 外參校正
- 外參 profile
- 外參啟用與切換
- 固定相機外參
- 旋臂運動模型
- 旋轉軸校正
- 馬達零點校正
- 世界座標校正
- 手動矩陣輸入

移除或遷移現有外參相關前後端模組，包含：

```text
CalibrationExtrinsics
CalibrationExtrinsicCreate
CalibrationExtrinsicStatus
CalibrationMotorControls

extrinsic_calibration_service.py
extrinsic_solver.py
motion_model.py
rotation_axis_solver.py
observation_graph.py
world_alignment.py
```

可被分析流程重用的數學函式應遷移至 `backend/app/analysis/pose_alignment/`，不得保留成使用者可操作的外參校正系統。

---

## 3. ArUco 基準設定

在系統設定加入：

```text
ArUco 基準
```

裝置底部四角各固定一個不同 ID 的 ArUco 標記，四個標記共同定義毫米世界座標。

設定包含：

- ArUco dictionary
- 四個 marker ID
- marker 邊長 `mm`
- 左右中心距離 `mm`
- 前後中心距離 `mm`
- marker 朝向
- 世界原點位置
- X、Y、Z 軸方向

介面必須提供俯視可視化圖示，清楚標示：

```text
左後 ID
右後 ID
左前 ID
右前 ID

標籤邊長
左右中心距離
前後中心距離
世界原點
```

距離一律定義為 marker 中心至中心，不得使用含糊的「間距」。

ArUco 設定需支援正方形與長方形配置，並允許進階模式直接指定每個 marker 中心的世界座標。

---

## 4. 相機安裝先驗

設定頁可保存以下選填資訊：

### 俯視相機

- 高度 `mm`
- 至平台中心水平距離 `mm`
- 面向中心的預估角度

### 側視相機

- 高度 `mm`
- 至平台中心水平距離 `mm`
- 面向中心的預估角度

### 旋臂相機

- 旋臂高度 `mm`，選填
- 馬達角度，自動讀取 Capture Record
- 相機面向與半徑，不要求手動填寫

這些資料只作為：

- 姿態初始值
- 合理性檢查
- 錯誤解排除
- ArUco 暫時不可見時的輔助

不得作為正式外參來源。

---

## 5. 分析時自動外參對齊

Analysis Run 新增階段：

```text
detecting_aruco
estimating_camera_poses
refining_camera_poses
```

執行流程：

```text
讀取各相機唯一內參
→ 讀取 ArUco 基準設定
→ 偵測每張影像中的 ArUco 角點
→ 建立世界 3D 點與影像 2D 點對應
→ 求解每張影像的旋轉與平移
→ 對齊至共同毫米世界座標
→ 使用 SfM / Bundle Adjustment 精修或補齊
→ 儲存資料集相機姿態
→ 繼續尖端追蹤與三維重建
```

`opencv_fisheye` 相機必須使用 fisheye 相容的去畸變與 PnP 流程。

---

## 6. 各相機姿態策略

### 俯視與側視相機

俯視與側視為固定相機。

每個 Analysis Run 仍自動從 ArUco 計算姿態，並可將多張有效影像的結果進行穩健平均。

同一 Analysis Run 內求得穩定姿態後，固定使用該結果，不必逐幀重新漂動。

### 旋臂相機

每張旋臂影像依序使用：

1. ArUco PnP 直接求解
2. SfM 與鄰近影像特徵匹配補齊
3. 馬達角度與前後影像姿態作為先驗
4. 選填旋臂高度作為合理性檢查

不得要求預先校正旋臂半徑、旋轉軸、零點或安裝矩陣。

---

## 7. SfM 的角色

SfM 不作為唯一尺度來源。

ArUco 提供：

- 世界原點
- 世界方向
- 毫米尺度
- 相機姿態初始值

SfM / Bundle Adjustment 負責：

- 精修相機姿態
- 補齊 ArUco 不可見的影像
- 提高跨影像一致性
- 將旋臂影像接入俯視與側視座標

若某張影像無法由 ArUco、SfM 或有效先驗取得姿態，必須標示失敗，不得生成虛構外參。

---

## 8. Analysis Run 資料

Analysis Run 不再保存：

```text
extrinsic_profile_id
active_extrinsic_calibration
```

改為保存：

```text
intrinsics_snapshot
aruco_layout_snapshot
camera_pose_results
pose_estimation_version
pose_quality
```

每張影像姿態需記錄來源：

```text
aruco
aruco_refined
sfm
motor_prior
unresolved
```

建議輸出：

```text
data/analysis/<analysis_id>/
├─ camera_poses.json
├─ aruco_alignment.json
├─ pose_quality.json
└─ pose_debug/
```

分析建立時必須快照當下內參與 ArUco 設定，確保日後設定修改不會改變舊 Analysis Run 的可重現性。

---

## 9. 品質驗證

至少計算：

- 每張影像可見 marker 數量
- ArUco 重投影誤差
- PnP inlier 數量
- 相機姿態來源
- SfM 註冊成功率
- 固定相機姿態離散程度
- 旋臂姿態連續性
- 馬達角度與相機軌跡一致性
- 未解姿態影像數量

分析介面應顯示：

```text
ArUco 對齊：成功／部分成功／失敗
已定位影像：N / Total
平均重投影誤差：px
SfM 補齊影像：N
未解影像：N
```

---

## 10. 完成條件

1. 校正頁面只包含內參校正。
2. 所有外參 profile 與外參切換介面已移除。
3. 設定頁可配置四個 ArUco 的尺寸、ID 與幾何位置。
4. ArUco 設定具有俯視可視化圖示。
5. 俯視與側視相機安裝資訊為選填先驗。
6. 旋臂高度為選填，馬達角度自動取自 Capture Record。
7. 每個 Analysis Run 自動求出資料集專屬外參。
8. ArUco 提供共同世界座標與毫米尺度。
9. SfM 負責姿態精修與缺失補齊。
10. 每張影像可追溯其姿態來源與品質。
11. 分析輸出包含 `camera_poses.json`。
12. 舊 Analysis Run 不受後續設定變更影響。
13. 未能可靠求解的影像不得進入三維重建。

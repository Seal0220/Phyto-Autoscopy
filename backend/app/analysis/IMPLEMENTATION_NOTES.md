# CHLOROCULUS 整合式三鏡頭植物尖端分析實作註記

本目錄提供 `top_side`（頂+側）與 `top_side_rotating`（頂+側+環繞）。
前者保留 Ruiz-Melero 等人於 2024 年發表的植物尖端追蹤流程；後者以雙鏡頭
結果為基準，再依旋臂角度求得動態相機姿態，以局部偵測與穩健多視角最佳化
提升精度。環繞觀測無效時只捨棄該影格的精修，保留原本的雙鏡頭結果。

## 不可推導的參數

論文未公開或不足以唯一決定的數值，在 `backend/config/analysis.json` 中維持
`null`。建立分析時必須由使用者依實際資料設定，服務不會偷偷補入任意數值：

- MOG2 history、variance threshold、learning rate 與初始化影格數；
- morphology kernels 與俯視／側視最小輪廓面積；
- 光照切換面積與估計等待影格；
- 俯視／側視 ROI、植物基部、候選輪廓數與 ROI margin；
- epipolar 最大距離、Minimum Path adjacency；
- 線性插值最大缺口時間。

同樣地，論文沒有公開雙鏡頭棋盤內角點規格、實測 square size 或植物基部世界
座標轉換。Calibration Profile 因此強制要求：

- 個別相機棋盤內角點與實測 X/Y square size；
- 雙鏡頭棋盤內角點與實測 X/Y square size；
- 明確量測且經驗證的 `T_world_from_stereo` 4×4 rigid transform。

## CHLOROCULUS 工程選擇

- Minimum Path 在二值遮罩的拓樸保持骨架上建立 4 或 8 鄰接圖，使用 Dijkstra
  求最小成本路徑。邊權重固定為 inverse distance-transform，讓路徑偏向輪廓
  中心線；候選端點先受 epipolar 距離限制，再以離植物基部最長的 geodesic
  距離選擇尖端。這些圖細節是 CHLOROCULUS 實作選擇，不宣稱是論文未公開
  的原始程式碼。
- 動態 ROI 使用本影格被選輪廓的全域 bounding rectangle，再加上使用者提供的
  margin 並裁切至使用者設定的 hard-bound ROI；沒有可用輪廓時沿用上一個
  ROI，不猜測新的大小。
- 光照變化期間重建 MOG2 背景並輸出 `lighting_transition`；背景初始化輸出
  `background_initialization`。兩者都不產生有效尖端，光照切換也會阻斷插值。
- 校正畸變係數依 OpenCV 順序儲存為 `k1, k2, p1, p2, k3`，同時輸出命名映射。
- Calibration Profile 不再以像素解析度完全相同作為使用條件。每次分析會依
  `top`、`side`、`rotating` 各自的固定輸入解析度縮放 Camera Matrix、Projection Matrix
  與 Fundamental Matrix 的像素座標，原始 Calibration Profile 保持不可變。
  這項換算允許不同寬高與長寬比，但不能補償相機模式額外造成的感光元件裁切
  或視野改變；該情況仍可能降低實際精度。
- 論文的準確率、約 3.7 px、0.5 cm 與 8.3% 僅作比較背景，不作本系統的通過
  門檻、保證或自動品質結論。

## 資料與研究邊界

- 原始 Record 與 `data/captures` 永遠唯讀。分析只在 `data/analysis` 產生衍生
  資料；校正只在 `data/calibration` 產生 Profile 與預覽。
- `top_side` 必須使用 `top` 與 `side`；`top_side_rotating` 另要求具有角度資料的
  `rotating` 影像，以及包含旋轉軸、零度偏移、方向與動態外參的有效校正。
- 自動偵測、插值與人工修正分開保存，最終解析順序為 Manual、Automatic／
  Estimated、Interpolated、Missing／Invalid。
- 三維軌跡是觀測與測量結果，不能直接用來宣稱植物具有或不具有意識。

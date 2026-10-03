# Phyto-Autoscopy

**Phyto-Autoscopy 綠色自視症**是 CHLOROCULUS 多視角植物影像擷取與分析裝置的本機控制系統。系統除了捕捉與硬體控制，也提供固定雙鏡頭尖端標記分析，以及整合俯視、側視與旋臂視角的逐輪多視角三維重建、人工修正與跨輪運動分析。

## 系統架構

```text
Next.js — 127.0.0.1:22223
FastAPI — 127.0.0.1:22222
```

瀏覽器只會連線至 Next.js，不會取得 FastAPI 連接埠、後端憑證或硬體 API 網址。Next.js 透過 `/api/*` 提供受限制的同源路由，並代理需要驗證的 `/ws/status` WebSocket 路徑。

```text
frontend/  Next.js App Router、JavaScript、Tailwind CSS v4 與 BFF Route Handlers
backend/   FastAPI API、硬體服務、設定與測試
data/      擷取影像、快照、分析結果、SQLite、校正、日誌與暫存資料
start.bat  在兩個獨立終端中啟動前端與後端，完成後自行結束
```

FastAPI 僅提供 API，不會掛載舊有的 Jinja 頁面。所有 `/api/*` 端點皆要求私有 BFF 憑證，並攜帶已驗證的操作者與角色資訊，同時套用權限檢查、速率限制及輸入驗證。所有會變更狀態的操作都會寫入 `data/logs/audit.jsonl`。WebSocket 連線使用僅能使用一次且有效時間短暫的票證，票證只能透過已驗證的 BFF 取得。

## 頂層功能

登入後介面分為四個公開路由：

- `/capture`：既有影像預覽、擷取、排程、直接控制、系統狀態與紀錄。
- `/analysis`：可分析紀錄、Analysis Run、人工修正、三維重建與結果匯出。
- `/calibration`：獨立的統一相機校正工作區，可管理三顆相機各自的唯一內參與多組外參校正檔。
- `/models`：模型資料的獨立入口；每輪分析所建立的 Gaussian、點雲與骨架仍歸屬於對應的 Analysis Run。

瀏覽器仍只呼叫 Next.js 的同源 `/api/*`。分析與校正工作透過 BFF 呼叫 FastAPI，長時間分析由後端 Worker 執行並將狀態保存於 SQLite，不會佔用單一 HTTP 請求，也不會阻塞馬達緊急停止。

## 分析與校正資料

分析輸入固定以 `data/captures/` 為唯讀來源。系統不會覆寫擷取影像或捕捉紀錄；不同輸出分別保存在：

```text
data/calibration/  相機內參、畸變係數、統一外參校正檔、品質報告與預覽
data/analysis/     每個 Analysis Run 的 Round、姿態、模型、尖端標記、軌跡與日誌
```

分析建立流程只使用已保存的捕捉紀錄：選擇 Record、擷取模式與相機視角後，自動掃描正式的 Mode／Round／Snapshot 階層。正式方法識別碼只使用：

大量影像的來源掃描在後端背景執行，建立頁會顯示進度並可取消；預覽只回傳有限筆 Round 明細，避免數千張影像使單次 HTTP 回應逾時。掃描期間請勿搬移或更改該筆擷取紀錄。

- `fixed`：使用俯視與側視影像建立雙鏡頭三維尖端標記與跨輪軌跡，不建立環繞三維植物模型。
- `rotating`：保留同一 Round 的全部有效旋臂視角，與俯視、側視影像共同建立每輪三維植物模型、尖端標記及跨輪軌跡。

兩種方法都會先依各實體相機的內參快照完成去畸變。新分析不需要 ArUco 世界標籤：俯視與側視影像以共同特徵求相對姿態，使用操作者輸入的**實測雙鏡頭光學中心距離**固定毫米尺度，並使用俯視鏡頭至平台的實測高度將平台設為世界 `Z=0`。相機姿態設定另可選填側鏡頭光學中心距桌面的高度及至分析原點的水平距離；這些量測會與影像估計的側鏡頭位置比對並顯示誤差，不會直接覆寫影像估得的姿態。側視姿態會檢查內點、重投影、視差與偏水平角；不符合門檻就停止，不輸出假定為公制的模型。`rotating` 再以雙鏡頭三維特徵逐張求旋臂姿態，必要時僅在前後有效姿態之間依馬達角度補足，然後透過 `gsplat_3dgs` 或 `graphdeco_3dgs` 建模。固定雙鏡頭姿態、內參與實測尺度在多視角精修時保持不變。建立分析介面可調整幾何與品質門檻、模型後端、訓練步數及 gsplat 影像縮小倍率。

每個成功的 `rotating` Round 可依建立分析時的選項分別輸出完整場景、純植物與背景 Gaussian 模型，以及完整場景、純植物與背景點雲、植物骨架、模型預覽、三維尖端標記、重投影品質與跨 Round 軌跡。未選取的選配輸出不會保留；必要的內部中間檔在分析完成後會清理。模型工作由獨立程序執行，單一 Round 失敗不會刪除其他已完成 Round。

校正由獨立的 `/calibration` 工作區完成，分析只讀取目前啟用且已驗證的內參快照。設定檔可版本化與重用；系統以 CM1.3M30M12Q（AR0130、FL 2.1 mm、FOV(D) 126°）作硬體初始資料，實際內參與畸變仍由校正影像求得。無標記流程不會宣稱已取得未量測的旋臂軸心或相機外參；人工修正會另存歷史紀錄，不會覆寫自動偵測結果。

論文沒有提供、或必須依實際裝置與資料決定的參數，在 `backend/config/analysis.json` 中保持 `null`。建立分析前必須由使用者明確輸入；校正棋盤尺寸與世界座標轉換也必須使用實際量測值，不能把論文數字當成未經確認的實體規格。

分析輸出是可檢查的測量結果，不直接宣稱植物具有或不具有意識，也不加入深度學習、Kalman Filter、Optical Flow 或其他不屬於本階段方法的追蹤器。

### 無損影像與 GPU 掃描

新拍的擷取影像與單張快照使用無損 LZW TIFF；即時預覽仍是 JPEG 串流。來源掃描可選用 NVIDIA nvImageCodec／nvTIFF 在 GPU 解碼 TIFF；沒有支援的 GPU 或未安裝套件時會回退 CPU。舊 PNG 在未轉換前仍能用 CPU 讀取。掃描結果會列出實際使用 GPU、CPU 解碼的張數，不能僅憑已安裝 CUDA 就認定掃描已使用 GPU。[NVIDIA nvImageCodec](https://github.com/NVIDIA/nvImageCodec)、[nvTIFF 格式支援](https://docs.nvidia.com/cuda/nvtiff/)。

GPU 套件不是 `--setup` 的基本依賴；依該電腦的 CUDA 主版本選擇安裝其中一組：

```powershell
.\.venv\Scripts\python.exe -m pip install "nvidia-nvimgcodec-cu12[nvtiff]"
# 或 CUDA 13：
.\.venv\Scripts\python.exe -m pip install "nvidia-nvimgcodec-cu13[nvtiff]"
```

既有的 PNG 擷取紀錄可使用一次性遷移工具。先停止前後端並備份 `data/`，再於專案根目錄查看計畫；確認磁碟空間足夠後才執行轉換：

```powershell
.\.venv\Scripts\python.exe backend\scripts\migrate_capture_png_to_tiff.py
.\.venv\Scripts\python.exe backend\scripts\migrate_capture_png_to_tiff.py --apply
```

工具逐張以像素比對驗證 TIFF，保留原 PNG 以維持既有 Analysis Run 的舊路徑，並將擷取索引、SQLite 與影像命名配置更新為 TIFF。原檔及原始 SQLite／索引備份保存在 `data/migration-backups/`；轉換失敗時請勿手動刪除備份或 PNG。其他電腦的資料可在該電腦執行相同命令；非預設資料目錄可傳入 `--data-root`。遷移不會在啟動服務時自動執行。

## 啟動方式

第一次使用時，請先在專案根目錄建立完整的依賴環境：

```bash
.\start.bat --setup
```

`--setup` 會在尚未建立時將 `.env.example` 複製為已被 Git 忽略的根目錄 `.env`，且不會覆寫既有的 `.env`。它也會建立根目錄 `.venv`、依照 `backend/requirements.txt` 安裝或同步後端 Python 相依套件，並透過 `npm install` 安裝或同步前端相依套件。設定完成後不會啟動任何服務。

`backend/config/*.json` 是每台電腦獨立的設定，`data/` 保存執行產生的紀錄；兩者不納入 Git。首次啟動後端時會根據程式內的預設值補齊缺少的設定檔，既有設定不會被覆寫。換機或更新至此版本前，請先在該電腦備份 `backend/config/` 與 `data/`；若 Git 因舊版已追蹤的設定檔而拒絕更新，先保存該電腦的設定變更，再更新程式並放回設定檔。

請替換 `.env` 中的三個私有預留值，接著以預設的正式模式啟動：

```bash
.\start.bat
```

不帶參數時固定使用正式模式，會先執行 `next build`，接著執行 `next start`，並在不啟用 reload 的情況下啟動 FastAPI。

一般啟動不會自行建立環境或安裝套件；若缺少 `.env`、`.venv` 或 `frontend/node_modules`，會提示先執行 `--setup`。

需要使用開發模式時，執行：

```bash
.\start.bat --mock
```

`--mock` 只切換開發啟動方式：前端執行 `next dev`，FastAPI 使用 `uvicorn --reload`。相機、馬達與其他功能不會被停用或替換，仍可直接使用實體硬體。

`start.bat` 會分別建立前端與後端終端，兩者都成功啟動後便自行結束，不會持續監控或占用第三個終端。FastAPI 與 Next.js 也不會互相啟動、停止或監控；需要停止服務時，請分別關閉其終端。

後端的 `backend/config/default.json` 只保存相對於專案根目錄的資料路徑，預設統一位於 `data/`。系統不使用路徑映射，也不保存與特定電腦綁定的絕對位置。若升級前仍有 `backend/data/`，下一次手動啟動後端時會在開啟 SQLite 前自動合併至專案根目錄的 `data/`，既有擷取、快照與日誌不會被覆寫；完成後會移除空的舊目錄。

只需開啟：

```text
http://127.0.0.1:22223
```

## 環境變數

共用硬體路徑與私有憑證應放在根目錄的 `.env`。FastAPI 與 Next.js 伺服器會各自載入此檔案；`start.bat` 不會透過其中一個服務替另一個服務注入環境變數。`frontend/.env.example` 記錄了前端伺服器端可選用的覆寫設定。請勿將後端位址、硬體路徑、憑證或密鑰放入任何 `NEXT_PUBLIC_*` 變數。

## 遠端操作

請勿將連接埠 `22223` 或 `22222` 直接暴露至網際網路。應透過反向代理或安全閘道器發布單一 HTTPS/WSS 入口，例如 `https://phyto.example.com`，並搭配 VPN 或 Zero Trust 存取、強式使用者驗證、TLS、權限管理及稽核檢視。兩個本機應用程式連接埠都應在閘道器後方維持綁定於 `127.0.0.1`。

## 硬體安全

馬達啟動時預設為釋放狀態。所有移動命令仍會受到後端針對角度、速度、加速度、電流及逾時所設定的軟體限制。`--mock` 是完整硬體可用的開發模式；在確認實體 CHLOROCULUS ARM 與接線正確之前，請勿送出移動命令。

## 測試

測試不需要保持服務執行。請在專案根目錄執行：

```bash
.\.venv\Scripts\python.exe -m pytest backend/tests
cd frontend
npm test
npm run build
```

後端測試涵蓋 Record／Mode／Round／View 分組、內參快照與 Fisheye 去畸變、ArUco 姿態、受約束姿態精修、多視角重建、模型輸出、尖端候選、穩健三角化、植物骨架、人工修正、跨輪軌跡與完整分析工作流程。前端測試與正式建置會驗證四步建立流程、BFF 契約、Round readiness、模型後端狀態、輸出設定與結果呈現。

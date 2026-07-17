# Phyto-Autoscopy

**Phyto-Autoscopy 綠色自視症**是 CHLOROCULUS 多視角植物影像擷取與分析裝置的本機控制系統。v0.2 在既有捕捉與硬體控制能力上，加入依 Ruiz-Melero 等人（2024）方法建立的固定俯視／側視植物主要生長尖端追蹤、人工修正與雙目三維重建流程。

## 系統架構

```text
瀏覽器
  ↓ HTTPS / WSS（部署於閘道器後方時）
Next.js BFF — 127.0.0.1:22223
  ↓ 私有的伺服器間請求 / WebSocket 轉送
FastAPI 硬體後端 — 127.0.0.1:22222
  ↓
相機、馬達、排程、設定、紀錄與本機檔案
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

登入後介面分為三個公開路由：

- `/capture`：既有影像預覽、擷取、排程、直接控制、系統狀態與紀錄。
- `/analysis`：可分析紀錄、相機校正、Analysis Run、人工修正、三維重建與結果匯出。
- `/models`：保留後續模型模組入口；v0.2 不實作模型訓練、COLMAP、NeRF 或 3D Gaussian Splatting。

瀏覽器仍只呼叫 Next.js 的同源 `/api/*`。分析與校正工作透過 BFF 呼叫 FastAPI，長時間分析由後端 Worker 執行並將狀態保存於 SQLite，不會佔用單一 HTTP 請求，也不會阻塞馬達緊急停止。

## 分析與校正資料

分析輸入固定以 `data/captures/` 為唯讀來源。系統不會覆寫擷取影像或捕捉紀錄；不同輸出分別保存在：

```text
data/calibration/  相機內參、畸變係數、雙目外參、品質報告與預覽
data/analysis/     每個 Analysis Run 的影格配對、偵測、修正、三維軌跡與日誌
```

分析建立流程不區分自動或手動來源：可由 Record 自動帶入 `top`、`side`、`rotating` 目錄，也可直接輸入目錄，掃描確認影像、解析度、配對與環繞角度後使用同一套分析管線。`top_side`（頂+側）保留論文的雙目方法；`top_side_rotating`（頂+側+環繞）先建立雙目基準點，再使用旋臂動態外參與局部偵測做穩健多視角精修。無效的環繞觀測只會停用該影格的精修，不會使整筆分析失敗。

校正是分析建立流程的一部分，設定檔可版本化與重用。系統以 CM1.3M30M12Q（AR0130、FL 2.1 mm、FOV(D) 126°）作硬體初始資料，實際內參與畸變仍由校正影像求得；進階方法另校正旋轉軸、零度偏移、方向與動態外參。人工修正會另存歷史紀錄，不會覆寫自動偵測結果。

論文沒有提供、或必須依實際裝置與資料決定的參數，在 `backend/config/analysis.json` 中保持 `null`。建立分析前必須由使用者明確輸入；校正棋盤尺寸與世界座標轉換也必須使用實際量測值，不能把論文數字當成未經確認的實體規格。

分析輸出是可檢查的測量結果，不直接宣稱植物具有或不具有意識，也不加入深度學習、Kalman Filter、Optical Flow 或其他不屬於本階段方法的追蹤器。

## 啟動方式

第一次使用時，請先在專案根目錄建立完整的依賴環境：

```bash
.\start.bat --setup
```

`--setup` 會在尚未建立時將 `.env.example` 複製為已被 Git 忽略的根目錄 `.env`，且不會覆寫既有的 `.env`。它也會建立根目錄 `.venv`、依照 `backend/requirements.txt` 安裝或同步後端 Python 相依套件，並透過 `npm install` 安裝或同步前端相依套件。設定完成後不會啟動任何服務。

請替換 `.env` 中的三個私有預留值，接著以預設的正式模式啟動：

```bash
.\start.bat
```

不帶參數時固定使用正式模式，會先執行 `next build`，接著執行 `next start`，並在不啟用 reload 的情況下啟動 FastAPI。

一般啟動不會自行建立環境或安裝套件；若缺少 `.env`、`.venv` 或 `frontend/node_modules`，會提示先執行 `--setup`。

需要使用模擬硬體進行安全開發時，執行：

```bash
.\start.bat --mock
```

`--mock` 就是開發模式：前端執行 `next dev`，FastAPI 使用 `uvicorn --reload`，並啟用模擬相機與馬達。

`start.bat` 會分別建立前端與後端終端，兩者都成功啟動後便自行結束，不會持續監控或占用第三個終端。FastAPI 與 Next.js 也不會互相啟動、停止或監控；需要停止服務時，請分別關閉其終端。

後端一律以專案根目錄的 `data/` 作為資料根目錄。若升級前仍有 `backend/data/`，下一次手動啟動後端時會在開啟 SQLite 前自動合併至根目錄 `data/`，既有擷取、快照與日誌不會被覆寫；完成後會移除空的舊目錄。

只需開啟：

```text
http://127.0.0.1:22223
```

請勿直接瀏覽 FastAPI。連接埠 `22222` 只綁定於本機回送位址，是 BFF 與硬體後端之間的私有邊界。

## 環境變數

共用硬體路徑與私有憑證應放在根目錄的 `.env`。FastAPI 與 Next.js 伺服器會各自載入此檔案；`start.bat` 不會透過其中一個服務替另一個服務注入環境變數。`frontend/.env.example` 記錄了前端伺服器端可選用的覆寫設定。請勿將後端位址、硬體路徑、憑證或密鑰放入任何 `NEXT_PUBLIC_*` 變數。

## 遠端操作

請勿將連接埠 `22223` 或 `22222` 直接暴露至網際網路。應透過反向代理或安全閘道器發布單一 HTTPS/WSS 入口，例如 `https://phyto.example.com`，並搭配 VPN 或 Zero Trust 存取、強式使用者驗證、TLS、權限管理及稽核檢視。兩個本機應用程式連接埠都應在閘道器後方維持綁定於 `127.0.0.1`。

## 硬體安全

馬達啟動時預設為釋放狀態。所有移動命令仍會受到後端針對角度、速度、加速度、電流及逾時所設定的軟體限制。在確認實體 CHLOROCULUS ARM 與接線正確之前，請先使用 `--mock` 模式。

## 測試

測試不需要保持服務執行。請在專案根目錄執行：

```bash
.\.venv\Scripts\python.exe -m pytest backend/tests
cd frontend
npm test
npm run build
```

後端測試涵蓋影格配對、相機校正、MOG2、光照切換、尖端候選、Epipolar 約束、Minimum Path、線性插值、三角化、重投影與完整分析工作流程。前端測試與正式建置會驗證路由、BFF 契約、分析資料轉換及既有捕捉功能。

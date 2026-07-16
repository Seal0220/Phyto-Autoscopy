# Phyto-Autoscopy

**Phyto-Autoscopy 綠色自視症**是 CHLOROCULUS 多視角植物影像擷取裝置的本機控制系統。

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
data/      擷取影像、快照、SQLite、校正、日誌與暫存資料
start.bat  在兩個獨立終端中啟動前端與後端，完成後自行結束
```

FastAPI 僅提供 API，不會掛載舊有的 Jinja 頁面。所有 `/api/*` 端點皆要求私有 BFF 憑證，並攜帶已驗證的操作者與角色資訊，同時套用權限檢查、速率限制及輸入驗證。所有會變更狀態的操作都會寫入 `data/logs/audit.jsonl`。WebSocket 連線使用僅能使用一次且有效時間短暫的票證，票證只能透過已驗證的 BFF 取得。

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

import Button from "@/components/buttons/Button";
import { Panel, PanelHeader } from "@/components/panels/Panel";
import SettingsGear from "@/components/panels/SettingsGear";
import { formatDateTime } from "@/lib/formatUtils";

import StorageSettings from "./components/StorageSettings";

export default function RecordsStorage({
  records,
  loading,
  scheduleActive,
  storageDirectory,
  open,
  onToggle,
  onNotify,
  onLoad,
}) {
  return (
    <Panel
      id="records-storage"
      className="min-[981px]:col-start-1 min-[981px]:row-start-4 [scroll-margin-top:5.6rem] max-[980px]:[scroll-margin-top:8.8rem]"
      aria-label="紀錄與儲存"
    >
      <PanelHeader
        title="紀錄與儲存"
        action={(
          <div className="flex items-center gap-2">
            <Button
              onClick={() => void onLoad()}
              disabled={loading}
            >
              {loading ? "讀取中…" : "重新整理"}
            </Button>
            <SettingsGear
              label="儲存"
              open={open}
              onClick={onToggle}
            />
          </div>
        )}
      />
      <div className="grid gap-1 border-b border-white/10 px-5 py-4 max-sm:px-4">
        <span className="text-xs font-black text-neutral-400">目前排程儲存位置</span>
        <code className="min-w-0 overflow-x-auto text-sm font-bold text-neutral-100">
          {storageDirectory || "尚未取得儲存位置。"}
        </code>
      </div>
      <div className="overflow-x-auto p-5 max-sm:p-4">
        <table className="w-full min-w-[38rem] border-collapse text-left text-sm">
          <thead>
            <tr className="border-b border-white/10 bg-white/[0.03] text-[11px] font-black tracking-[0.12em] text-neutral-400">
              <th className="px-4 py-3">紀錄識別碼</th>
              <th className="px-4 py-3">狀態</th>
              <th className="px-4 py-3">建立時間</th>
              <th className="px-4 py-3">匯出</th>
            </tr>
          </thead>
          <tbody>
            {records.length ? records.map((record) => (
              <tr
                className="border-b border-white/10 text-neutral-200 last:border-b-0"
                key={record.session_id}
              >
                <td className="px-4 py-3.5">{record.session_id}</td>
                <td className="px-4 py-3.5">{record.status}</td>
                <td className="px-4 py-3.5">{formatDateTime(record.created_at)}</td>
                <td className="px-4 py-3.5">
                  <div className="flex gap-3">
                    <a
                      className="font-black text-emerald-200 hover:text-emerald-100"
                      href={`/api/sessions/${encodeURIComponent(record.session_id)}/metadata`}
                    >
                      CSV
                    </a>
                    <a
                      className="font-black text-emerald-200 hover:text-emerald-100"
                      href={`/api/sessions/${encodeURIComponent(record.session_id)}/session-json`}
                    >
                      JSON
                    </a>
                  </div>
                </td>
              </tr>
            )) : (
              <tr>
                <td
                  className="px-4 py-5 text-neutral-400"
                  colSpan="4"
                >
                  尚無紀錄。
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      <StorageSettings
        onNotify={onNotify}
        open={open}
        locked={scheduleActive}
      />
    </Panel>
  );
}

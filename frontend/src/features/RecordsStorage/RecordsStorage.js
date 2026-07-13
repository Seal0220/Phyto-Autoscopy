import { FiRefreshCw } from "react-icons/fi";

import Button from "@/components/buttons/Button";
import { Panel, PanelHeader } from "@/components/panels/Panel";
import SettingsGear from "@/components/panels/SettingsGear";
import { formatDateTime } from "@/lib/formatUtils";

import RecordsStorageSettings from "./components/RecordsStorageSettings";

export default function RecordsStorage({
  records,
  loading,
  scheduleActive,
  open,
  onToggle,
  onNotify,
  onLoad,
}) {
  return (
    <Panel
      id="records-storage"
      className="min-[981px]:col-start-1 min-[981px]:row-start-5 [scroll-margin-top:5.6rem] max-[980px]:[scroll-margin-top:8.8rem]"
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
              <FiRefreshCw
                className="size-4 shrink-0"
                aria-hidden="true"
              />
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
      <div className="p-5 max-sm:p-4">
        <div className="max-h-96 overflow-auto">
          <table className="w-full min-w-256 border-collapse text-left text-sm">
            <thead className="sticky top-0 z-10 bg-[#07130f]/95 backdrop-blur-xl">
              <tr className="border-b border-white/10 bg-white/[0.03] text-[11px] font-black tracking-[0.12em] text-neutral-400">
                <th className="px-4 py-3">ID</th>
                <th className="px-4 py-3">狀態</th>
                <th className="px-4 py-3">儲存位置</th>
                <th className="px-4 py-3">建立時間</th>
                <th className="px-4 py-3">結束時間</th>
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
                  <td className="min-w-72 max-w-96 px-4 py-3.5">
                    <code className="break-all text-xs font-bold text-neutral-300">
                      {record.session_path || "—"}
                    </code>
                  </td>
                  <td className="px-4 py-3.5 whitespace-nowrap">
                    {formatDateTime(record.created_at)}
                  </td>
                  <td className="px-4 py-3.5 whitespace-nowrap">
                    {record.ended_at ? formatDateTime(record.ended_at) : "—"}
                  </td>
                  <td className="px-4 py-3.5">
                    <div className="flex gap-3">
                      <a
                        className="font-black text-emerald-200 transition-colors duration-150 hover:text-emerald-100"
                        href={`/api/sessions/${encodeURIComponent(record.session_id)}/metadata`}
                      >
                        CSV
                      </a>
                      <a
                        className="font-black text-emerald-200 transition-colors duration-150 hover:text-emerald-100"
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
                    colSpan="6"
                  >
                    尚無紀錄。
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
      <RecordsStorageSettings
        onNotify={onNotify}
        open={open}
        locked={scheduleActive}
      />
    </Panel>
  );
}

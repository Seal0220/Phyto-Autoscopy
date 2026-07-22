"use client";

import {
  FiDownload,
  FiRefreshCw,
} from "react-icons/fi";

import Button from "@/components/buttons/Button";
import RetryMessage from "@/components/feedback/RetryMessage";
import { Panel, PanelHeader } from "@/components/panels/Panel";
import SettingsGear from "@/components/panels/SettingsGear";
import { formatDateTime } from "@/lib/formatUtils";

import RecordsStorageSettings from "./components/RecordsStorageSettings";
import useRecordExport from "./hooks/useRecordExport";
import { recordStatusLabel } from "./lib/storageUtils";

export default function RecordsStorage({
  records,
  loading,
  loadError,
  scheduleActive,
  open,
  onToggle,
  onNotify,
  onLoad,
}) {
  const {
    exportingKeys,
    exportRecord,
  } = useRecordExport({
    onNotify,
  });

  return (
    <Panel
      id="records-storage"
      className="min-[981px]:col-start-1 min-[981px]:row-start-5 [scroll-margin-top:8.75rem] max-[980px]:[scroll-margin-top:11.5rem]"
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
        {!loading && loadError && !records.length ? (
          <RetryMessage
            message={loadError}
            onRetry={() => void onLoad()}
            retrying={loading}
          />
        ) : (
          <div className="max-h-96 overflow-auto">
          <table className="w-full min-w-256 border-collapse text-left text-sm">
            <thead className="sticky top-0 z-10 bg-[#07130f]/95 backdrop-blur-xl">
              <tr className="border-b border-white/15 bg-white/[0.03] text-[11px] font-black tracking-[0.12em] text-neutral-400">
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
                  className="border-b border-white/15 text-neutral-200 last:border-b-0"
                  key={record.record_id}
                >
                  <td className="px-4 py-3.5">{record.record_id}</td>
                  <td className="px-4 py-3.5">{recordStatusLabel(record.status)}</td>
                  <td className="min-w-72 max-w-96 px-4 py-3.5">
                    <code className="break-all text-xs font-bold text-neutral-300">
                      {record.record_path || "—"}
                    </code>
                  </td>
                  <td className="px-4 py-3.5 whitespace-nowrap">
                    {formatDateTime(record.created_at)}
                  </td>
                  <td className="px-4 py-3.5 whitespace-nowrap">
                    {record.ended_at ? formatDateTime(record.ended_at) : "—"}
                  </td>
                  <td className="px-4 py-3.5">
                    <div className="flex gap-2">
                      <Button
                        className="min-h-8 rounded-lg px-2.5 py-1 text-xs"
                        disabled={exportingKeys.has(`${record.record_id}:csv`)}
                        onClick={() => void exportRecord(
                          record.record_id,
                          "csv",
                        )}
                      >
                        <FiDownload
                          className="size-3.5 shrink-0"
                          aria-hidden="true"
                        />
                        {exportingKeys.has(`${record.record_id}:csv`) ? "下載中…" : "CSV"}
                      </Button>
                      <Button
                        className="min-h-8 rounded-lg px-2.5 py-1 text-xs"
                        disabled={exportingKeys.has(`${record.record_id}:json`)}
                        onClick={() => void exportRecord(
                          record.record_id,
                          "json",
                        )}
                      >
                        <FiDownload
                          className="size-3.5 shrink-0"
                          aria-hidden="true"
                        />
                        {exportingKeys.has(`${record.record_id}:json`) ? "下載中…" : "JSON"}
                      </Button>
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
        )}
      </div>
      <RecordsStorageSettings
        onNotify={onNotify}
        open={open}
        locked={scheduleActive}
      />
    </Panel>
  );
}

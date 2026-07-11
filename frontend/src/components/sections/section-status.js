import { Panel, PanelHeader, StatusPill } from "@/components/ui/panel";

const EXPERIMENT_STATUS_LABELS = {
  idle: "待命",
  running: "執行中",
  paused: "已暫停",
  stopped: "已停止",
  completed: "已完成",
  failed: "失敗",
};

function formatBytes(value) {
  if (!Number.isFinite(value)) return "—";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let unit = 0;
  let amount = value;
  while (amount >= 1024 && unit < units.length - 1) {
    amount /= 1024;
    unit += 1;
  }
  return `${amount.toFixed(unit === 0 ? 0 : 1)} ${units[unit]}`;
}

export default function StatusSection({ cameraMeta, cameraById, connection, experiment, system }) {
  const experimentStatus = experiment.status || "idle";
  const experimentTone = experimentStatus === "running" ? "success" : experimentStatus === "failed" ? "offline" : "neutral";
  const isConnected = connection === "connected";

  return (
    <Panel id="overview" className="[scroll-margin-top:5.6rem] max-[980px]:[scroll-margin-top:8.8rem]" aria-label="即時狀態">
      <PanelHeader title="即時狀態" />
      <div className="p-5 max-sm:p-4">
        <dl className="grid">
          <div className="flex items-center justify-between gap-3 border-b border-white/10 py-2.5 first:pt-0"><dt className="text-sm text-white/65">連接狀態</dt><dd><StatusPill tone={experimentTone}>{EXPERIMENT_STATUS_LABELS[experimentStatus] || experimentStatus}</StatusPill></dd></div>
          <div className="flex items-center justify-between gap-3 border-b border-white/10 py-2.5"><dt className="text-sm text-white/65">可用儲存空間</dt><dd><StatusPill>{formatBytes(system.disk?.free_bytes)}</StatusPill></dd></div>
          <div className="flex items-center justify-between gap-3 border-b border-white/10 py-2.5"><dt className="text-sm text-white/65">運行模式</dt><dd><StatusPill>{system.mock_mode ? "模擬模式" : "硬體模式"}</StatusPill></dd></div>
          <div className="flex items-center justify-between gap-3 border-b border-white/10 py-2.5"><dt className="text-sm text-white/65">即時通訊</dt><dd><StatusPill tone={isConnected ? "success" : "offline"}>{isConnected ? "連線已建立" : "連線離線"}</StatusPill></dd></div>
          {Object.entries(cameraMeta).map(([cameraId, meta]) => {
            const camera = cameraById.get(cameraId);
            const enabled = camera?.enabled ?? true;
            const connected = Boolean(camera?.connected);
            return <div className="flex items-center justify-between gap-3 py-2.5 last:pb-0" key={cameraId}><dt className="text-sm text-white/65">{meta.label}</dt><dd><StatusPill tone={enabled && connected ? "success" : "offline"}>{enabled ? "已啟用" : "未啟用"}・{connected ? "已連線" : "離線"}</StatusPill></dd></div>;
          })}
        </dl>
      </div>
    </Panel>
  );
}

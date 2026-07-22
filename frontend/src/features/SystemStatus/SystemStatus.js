import { Panel, PanelHeader, StatusPill } from "@/components/panels/Panel";
import {
  scheduleStatusLabel,
  scheduleStatusTone,
} from "@/features/Schedule/lib/scheduleUtils";
import { formatBytes } from "@/lib/formatUtils";

export default function SystemStatus({
  imagePreviewMeta,
  imagePreviewById,
  connection,
  motor,
  schedule,
  system,
}) {
  const scheduleState = schedule.status || "idle";
  const scheduleTone = scheduleStatusTone(scheduleState);
  const isConnected = connection === "connected";
  const motorConnected = Boolean(motor?.connected);
  const diskUnavailable = Boolean(system.disk?.error);

  return (
    <Panel
      id="system-status"
      className="scroll-mt-[8.75rem] max-[980px]:scroll-mt-[11.5rem]"
      aria-label="系統狀態"
    >
      <PanelHeader title="系統狀態" />
      <div className="p-5 max-sm:p-4">
        <dl className="grid">
          <div className="flex items-center justify-between gap-3 border-b border-white/15 py-2.5 first:pt-0">
            <dt className="text-sm text-neutral-400">排程狀態</dt>
            <dd>
              <StatusPill tone={scheduleTone}>
                {scheduleStatusLabel(scheduleState)}
              </StatusPill>
            </dd>
          </div>
          <div className="flex items-center justify-between gap-3 border-b border-white/15 py-2.5">
            <dt className="text-sm text-neutral-400">可用儲存空間</dt>
            <dd>
              <StatusPill tone={diskUnavailable ? "offline" : "neutral"}>
                {diskUnavailable ? "無法讀取" : formatBytes(system.disk?.free_bytes)}
              </StatusPill>
            </dd>
          </div>
          <div className="flex items-center justify-between gap-3 border-b border-white/15 py-2.5">
            <dt className="text-sm text-neutral-400">運行模式</dt>
            <dd>
              <StatusPill>
                {system.mock_mode ? "模擬模式" : "硬體模式"}
              </StatusPill>
            </dd>
          </div>
          <div className="flex items-center justify-between gap-3 border-b border-white/15 py-2.5">
            <dt className="text-sm text-neutral-400">即時通訊</dt>
            <dd>
              <StatusPill tone={isConnected ? "success" : "offline"}>
                {isConnected ? "連線已建立" : "連線離線"}
              </StatusPill>
            </dd>
          </div>
          <div className="flex items-center justify-between gap-3 border-b border-white/15 py-2.5">
            <dt className="text-sm text-neutral-400">馬達連接</dt>
            <dd>
              <StatusPill tone={motorConnected ? "success" : "offline"}>
                {motorConnected ? "已連接" : "未連接"}
              </StatusPill>
            </dd>
          </div>
          {Object.entries(imagePreviewMeta).map(([imagePreviewId, meta]) => {
            const imagePreview = imagePreviewById.get(imagePreviewId);
            const enabled = imagePreview?.enabled ?? true;
            const connected = Boolean(imagePreview?.connected);
            return (
              <div
                className="flex items-center justify-between gap-3 py-2.5 last:pb-0"
                key={imagePreviewId}
              >
                <dt className="text-sm text-neutral-400">{meta.label}</dt>
                <dd className="flex flex-wrap justify-end gap-2">
                  <StatusPill tone={enabled ? "success" : "offline"}>
                    {enabled ? "已啟用" : "未啟用"}
                  </StatusPill>
                  <StatusPill tone={connected ? "success" : "offline"}>
                    {connected ? "已連線" : "離線"}
                  </StatusPill>
                </dd>
              </div>
            );
          })}
        </dl>
      </div>
    </Panel>
  );
}

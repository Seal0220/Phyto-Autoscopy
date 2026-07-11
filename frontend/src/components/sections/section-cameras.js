import SettingsPanel from "@/components/settings-panel";
import Button from "@/components/ui/button";
import { Panel, PanelHeader, StatusPill } from "@/components/ui/panel";
import SettingsGear from "@/components/ui/settings-gear";

export default function CamerasSection({ cameraMeta, cameraById, isConnected, busyAction, open, onToggle, onRunAction, onNotify }) {
  return (
    <Panel id="cameras" className="col-span-full [scroll-margin-top:5.6rem] max-[980px]:[scroll-margin-top:8.8rem]" aria-label="相機預覽">
      <PanelHeader
        title="相機預覽"
        action={(
          <div className="flex items-center gap-2">
            <Button disabled={!isConnected || busyAction === "camera.capture_all"} onClick={() => void onRunAction("camera.capture_all", {}, "已擷取全部相機畫面。")}>
              全部擷取
            </Button>
            <SettingsGear label="相機" open={open} onClick={onToggle} />
          </div>
        )}
      />
      <div className="grid grid-cols-1 overflow-hidden border-y border-white/10 bg-black/10 min-[720px]:grid-cols-2 min-[1180px]:grid-cols-3">
        {Object.entries(cameraMeta).map(([cameraId, meta]) => {
          const camera = cameraById.get(cameraId);
          const enabled = camera?.enabled ?? true;
          const connected = Boolean(camera?.connected);
          return (
            <article className={`grid min-w-0 overflow-hidden border-b border-white/10 bg-black/10 last:border-b-0 min-[720px]:border-r min-[720px]:nth-[2n]:border-r-0 min-[1180px]:border-b-0 min-[1180px]:nth-[2n]:border-r min-[1180px]:nth-[3n]:border-r-0 ${enabled ? "" : "grayscale opacity-60"}`} key={cameraId}>
              <div className="relative min-h-0 overflow-hidden bg-black/35 p-2">
                <img className="block aspect-[4/3] w-full rounded-2xl bg-black/40 object-cover" src={`/api/cameras/${cameraId}/stream`} alt={`${meta.label} 即時預覽`} />
              </div>
              <footer className="flex min-h-[3.4rem] min-w-0 items-center gap-2 border-t border-white/10 bg-white/[0.035] px-3 py-2">
                <StatusPill tone={enabled ? "success" : "offline"}>{enabled ? "已啟用" : "未啟用"}</StatusPill>
                <StatusPill tone={connected ? "success" : "warning"}>{connected ? "已連線" : "離線"}</StatusPill>
                <span className="min-w-0 flex-1 overflow-hidden text-xs font-extrabold text-white text-ellipsis whitespace-nowrap" title={meta.device}>{meta.label}</span>
                <div className="flex shrink-0 gap-1">
                  <Button className="hidden min-h-8 rounded-lg px-2.5 py-1 text-xs" disabled={!isConnected || !enabled || busyAction === "camera.capture"} onClick={() => void onRunAction("camera.capture", { camera_id: cameraId }, `${meta.label} 已擷取。`)}>擷取</Button>
                  <Button className="min-h-8 rounded-lg px-2.5 py-1 text-xs" disabled={!isConnected || !enabled || busyAction === "camera.reconnect"} onClick={() => void onRunAction("camera.reconnect", { camera_id: cameraId }, `${meta.label} 已要求重新連線。`)}>重新連線</Button>
                </div>
              </footer>
            </article>
          );
        })}
      </div>
      <SettingsPanel group="cameras" label="相機" onNotify={onNotify} open={open} />
    </Panel>
  );
}

import Button from "@/components/buttons/Button";
import {
  Panel,
  PanelHeader,
  StatusPill,
} from "@/components/panels/Panel";
import SettingsGear from "@/components/panels/SettingsGear";
import { IMAGE_PREVIEW_META } from "@/features/ImagePreview/imagePreviewConfig";

import ImagePreviewSettings from "./components/ImagePreviewSettings";

export default function ImagePreview({
  imagePreviewById,
  isConnected,
  busyAction,
  scheduleActive,
  open,
  onToggle,
  onRunAction,
  onNotify,
}) {
  return (
    <Panel
      id="image-preview"
      className="col-span-full scroll-mt-[5.6rem] max-[980px]:scroll-mt-[8.8rem]"
      aria-label="影像預覽"
    >
      <PanelHeader
        title="影像預覽"
        action={(
          <div className="flex items-center gap-2">
            <Button
              variant="primary"
              disabled={!isConnected || scheduleActive || busyAction === "camera.capture_all"}
              onClick={() => void onRunAction("camera.capture_all", {}, "已擷取全部影像。")}
            >
              擷取全部影像
            </Button>
            <SettingsGear
              label="影像預覽"
              open={open}
              onClick={onToggle}
            />
          </div>
        )}
      />
      <div className="grid grid-cols-1 overflow-hidden border-y border-white/10 bg-black/10 min-[720px]:grid-cols-2 min-[1180px]:grid-cols-3">
        {Object.entries(IMAGE_PREVIEW_META).map(([
          imagePreviewId,
          meta,
        ]) => {
          const imagePreview = imagePreviewById.get(imagePreviewId);
          const enabled = imagePreview?.enabled ?? true;
          const connected = Boolean(imagePreview?.connected);

          return (
            <article
              className={`grid min-w-0 overflow-hidden border-b border-white/10 bg-black/10 last:border-b-0 min-[720px]:border-r min-[720px]:nth-[2n]:border-r-0 min-[1180px]:border-b-0 min-[1180px]:nth-[2n]:border-r min-[1180px]:nth-[3n]:border-r-0 ${enabled ? "" : "grayscale opacity-60"}`}
              key={imagePreviewId}
            >
              <div className="relative min-h-0 overflow-hidden bg-black/35 p-2">
                <img
                  className="block aspect-4/3 w-full rounded-2xl bg-black/40 object-cover"
                  src={`/api/cameras/${imagePreviewId}/stream`}
                  alt={`${meta.label} 即時預覽`}
                />
              </div>
              <footer className="flex min-h-[3.4rem] min-w-0 flex-wrap items-center gap-2 border-t border-white/10 bg-white/[0.035] px-3 py-2">
                <div className="flex min-w-0 items-center gap-2">
                  <StatusPill tone={enabled ? "success" : "offline"}>
                    {enabled ? "已啟用" : "未啟用"}
                  </StatusPill>
                  <StatusPill tone={connected ? "success" : "warning"}>
                    {connected ? "已連線" : "離線"}
                  </StatusPill>
                  <span
                    className="min-w-0 flex-1 overflow-hidden text-xs font-extrabold text-white text-ellipsis whitespace-nowrap"
                    title={meta.device}
                  >
                    {meta.label}
                  </span>
                </div>
                <div className="ml-auto flex shrink-0 gap-2 items-center">
                  <Button
                    className="min-h-8 rounded-lg px-2.5 py-1 text-xs"
                    variant="primary"
                    disabled={
                      !isConnected
                      || !enabled
                      || !connected
                      || scheduleActive
                      || busyAction === "camera.capture"
                    }
                    onClick={() => void onRunAction(
                      "camera.capture",
                      { camera_id: imagePreviewId },
                      `${meta.label} 已擷取單張影像。`,
                    )}
                  >
                    擷取
                  </Button>
                  <Button
                    className="min-h-8 rounded-lg px-2.5 py-1 text-xs"
                    disabled={!isConnected || !enabled || busyAction === "camera.reconnect"}
                    onClick={() => void onRunAction(
                      "camera.reconnect",
                      { camera_id: imagePreviewId },
                      `${meta.label} 已要求重新連線。`,
                    )}
                  >
                    重新連線
                  </Button>
                </div>
              </footer>
            </article>
          );
        })}
      </div>
      <ImagePreviewSettings
        onNotify={onNotify}
        open={open}
        locked={scheduleActive}
      />
    </Panel>
  );
}

"use client";

import {
  useEffect,
  useState,
} from "react";
import {
  FiCamera,
  FiRefreshCw,
} from "react-icons/fi";

import Button from "@/components/buttons/Button";
import CameraStream from "@/components/media/CameraStream";
import {
  Panel,
  PanelHeader,
  StatusPill,
} from "@/components/panels/Panel";
import SettingsGear from "@/components/panels/SettingsGear";
import { IMAGE_PREVIEW_META } from "@/features/ImagePreview/imagePreviewConfig";

import ImagePreviewSettings from "./components/ImagePreviewSettings";

function validCalibrationIds(intrinsics) {
  return new Set(
    Array.isArray(intrinsics)
      ? intrinsics
        .filter((item) => item?.status === "valid")
        .map((item) => item.camera_id)
      : [],
  );
}

export default function ImagePreview({
  imagePreviewById,
  busyActions,
  scheduleActive,
  open,
  onToggle,
  onRunAction,
  onNotify,
}) {
  const [calibratedCameraIds, setCalibratedCameraIds] = useState(
    () => new Set(),
  );
  const cameraBusy = [...busyActions].some((action) => action.startsWith("camera."));

  useEffect(() => {
    let mounted = true;

    async function loadCalibrations() {
      try {
        const response = await fetch("/api/calibration/intrinsics", {
          cache: "no-store",
        });
        if (!response.ok) {
          throw new Error("讀取相機校正狀態失敗。");
        }
        const intrinsics = await response.json();
        if (mounted) {
          setCalibratedCameraIds(validCalibrationIds(intrinsics));
        }
      } catch (error) {
        if (mounted) {
          setCalibratedCameraIds(new Set());
          onNotify?.(
            error instanceof Error
              ? error.message
              : "讀取相機校正狀態失敗。",
            "error",
          );
        }
      }
    }

    void loadCalibrations();
    return () => {
      mounted = false;
    };
  }, [onNotify]);

  return (
    <Panel
      id="camera"
      className="col-span-full scroll-mt-[8.75rem] max-[980px]:scroll-mt-[11.5rem]"
      aria-label="攝影機"
    >
      <PanelHeader
        title="攝影機"
        action={(
          <div className="flex flex-wrap items-center justify-end gap-2 max-sm:w-full">
            <Button
              variant="primary"
              disabled={
                scheduleActive
                || cameraBusy
              }
              onClick={() => void onRunAction(
                "camera.snapshot_all",
                {},
                "已將全部相機的單張影像儲存至快照目錄。",
              )}
            >
              <FiCamera
                className="size-4 shrink-0"
                aria-hidden="true"
              />
              擷取全部
            </Button>
            <Button
              disabled={cameraBusy}
              onClick={() => void onRunAction(
                "camera.reconnect_all",
                {},
                "已要求重新連線全部相機。",
              )}
            >
              <FiRefreshCw
                className="size-4 shrink-0"
                aria-hidden="true"
              />
              重新連線全部
            </Button>
            <SettingsGear
              label="攝影機"
              open={open}
              onClick={onToggle}
            />
          </div>
        )}
      />
      <div className="grid grid-cols-1 overflow-hidden border-y border-white/15 bg-black/15 min-[720px]:grid-cols-2 min-[1180px]:grid-cols-3">
        {Object.entries(IMAGE_PREVIEW_META).map(([
          imagePreviewId,
          meta,
        ]) => {
          const imagePreview = imagePreviewById.get(imagePreviewId);
          const enabled = imagePreview?.enabled ?? true;
          const connected = Boolean(imagePreview?.connected);

          return (
            <article
              className={`
                grid min-w-0 overflow-hidden border-b border-white/15 bg-black/15 last:border-b-0 min-[720px]:border-r min-[720px]:nth-[2n]:border-r-0 min-[1180px]:border-b-0 min-[1180px]:nth-[2n]:border-r min-[1180px]:nth-[3n]:border-r-0
                ${enabled ? "" : "grayscale opacity-60"}
              `}
              key={imagePreviewId}
            >
              <CameraStream
                cameraId={imagePreviewId}
                label={meta.label}
                device={meta.device}
                enabled={enabled}
                connected={connected}
                actualFps={imagePreview?.actual_fps}
                calibrated={calibratedCameraIds.has(imagePreviewId)}
                onNotify={onNotify}
              />
              <footer className="flex min-h-[3.4rem] min-w-0 flex-wrap items-center gap-2 border-t border-white/15 bg-white/[0.035] px-3 py-2">
                <div className="flex min-w-0 items-center gap-2">
                  <StatusPill tone={enabled ? "success" : "offline"}>
                    {enabled ? "已啟用" : "未啟用"}
                  </StatusPill>
                  <StatusPill tone={connected ? "success" : "warning"}>
                    {connected ? "已連線" : "離線"}
                  </StatusPill>
                </div>
                <div className="ml-auto flex shrink-0 gap-2 items-center">
                  <Button
                    className="min-h-8 rounded-lg px-2.5 py-1 text-xs"
                    variant="primary"
                    disabled={
                      !enabled
                      || !connected
                      || scheduleActive
                      || cameraBusy
                    }
                    onClick={() => void onRunAction(
                      "camera.snapshot",
                      { camera_id: imagePreviewId },
                      `${meta.label}單張影像已儲存至快照目錄。`,
                    )}
                  >
                    <FiCamera
                      className="size-3.5 shrink-0"
                      aria-hidden="true"
                    />
                    擷取
                  </Button>
                  <Button
                    className="min-h-8 rounded-lg px-2.5 py-1 text-xs"
                    disabled={
                      !enabled
                      || cameraBusy
                    }
                    onClick={() => void onRunAction(
                      "camera.reconnect",
                      { camera_id: imagePreviewId },
                      `${meta.label} 已要求重新連線。`,
                    )}
                  >
                    <FiRefreshCw
                      className="size-3.5 shrink-0"
                      aria-hidden="true"
                    />
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

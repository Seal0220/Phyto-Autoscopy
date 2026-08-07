"use client";

import {
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";
import {
  FiAperture,
  FiRefreshCw,
} from "react-icons/fi";
import {
  PiCrosshairBold,
  PiRectangleDashedBold,
} from "react-icons/pi";

import Button from "@/components/buttons/Button";
import CameraGuideOverlay from "@/components/media/CameraGuideOverlay";
import FullscreenImage from "@/components/media/FullscreenImage";
import { messageFromError } from "@/lib/httpUtils";

const RETRY_DELAYS_MS = [1500, 3000, 5000];

function formatFps(value) {
  const fps = Number(value);
  return Number.isFinite(fps) && fps > 0
    ? String(Math.round(fps))
    : "0";
}

function formatExposure(value) {
  if (value === null || value === undefined || value === "") return "—";
  const exposure = Number(value);
  if (!Number.isFinite(exposure)) return "—";
  if (Number.isInteger(exposure)) return String(exposure);
  return exposure.toFixed(2).replace(/\.?0+$/, "");
}

export default function CameraStream({
  cameraId,
  label,
  device,
  enabled,
  connected,
  actualFps,
  width,
  height,
  exposureValue,
  meteringRegion,
  overexposedRegions,
  meteringRegionDisabled = false,
  calibrated = false,
  streamPath,
  onSaveMeteringRegion,
  onNotify,
}) {
  const [retryToken, setRetryToken] = useState(0);
  const [streamFailed, setStreamFailed] = useState(false);
  const [retryScheduled, setRetryScheduled] = useState(false);
  const [pageVisible, setPageVisible] = useState(true);
  const [undistortionEnabled, setUndistortionEnabled] = useState(false);
  const [crosshairVisible, setCrosshairVisible] = useState(false);
  const [exposureVisible, setExposureVisible] = useState(false);
  const [editableMeteringRegion, setEditableMeteringRegion] = useState(
    meteringRegion,
  );
  const [meteringRegionSaving, setMeteringRegionSaving] = useState(false);
  const [frameSize, setFrameSize] = useState(() => ({
    width: Number(width) || 16,
    height: Number(height) || 9,
  }));
  const retryTimerRef = useRef(null);
  const retryCountRef = useRef(0);
  const failureNotifiedRef = useRef(false);
  const meteringRegionEditingRef = useRef(false);
  const meteringRegionSavingRef = useRef(false);

  const clearRetryTimer = useCallback(() => {
    window.clearTimeout(retryTimerRef.current);
    retryTimerRef.current = null;
    setRetryScheduled(false);
  }, []);

  const reloadStream = useCallback(() => {
    if (!enabled) return;
    clearRetryTimer();
    retryCountRef.current = 0;
    failureNotifiedRef.current = false;
    setStreamFailed(false);
    setRetryToken((current) => current + 1);
  }, [
    clearRetryTimer,
    enabled,
  ]);

  const handleStreamLoad = useCallback((event) => {
    if (!enabled) return;
    clearRetryTimer();
    retryCountRef.current = 0;
    failureNotifiedRef.current = false;
    setStreamFailed(false);
    const naturalWidth = Number(event?.currentTarget?.naturalWidth);
    const naturalHeight = Number(event?.currentTarget?.naturalHeight);
    if (naturalWidth > 0 && naturalHeight > 0) {
      setFrameSize((current) => (
        current.width === naturalWidth && current.height === naturalHeight
          ? current
          : {
            width: naturalWidth,
            height: naturalHeight,
          }
      ));
    }
  }, [
    clearRetryTimer,
    enabled,
  ]);

  const handleStreamError = useCallback(() => {
    if (!enabled) return;
    setStreamFailed(true);
    if (retryTimerRef.current) return;

    const retryDelay = RETRY_DELAYS_MS[retryCountRef.current];
    if (retryDelay !== undefined) {
      setRetryScheduled(true);
      retryTimerRef.current = window.setTimeout(() => {
        retryTimerRef.current = null;
        retryCountRef.current += 1;
        setRetryScheduled(false);
        setStreamFailed(false);
        setRetryToken((current) => current + 1);
      }, retryDelay);
      return;
    }

    if (!failureNotifiedRef.current) {
      failureNotifiedRef.current = true;
      onNotify?.(`${label}影像串流載入失敗，請重新載入或重新連線相機。`, "error");
    }
  }, [
    enabled,
    label,
    onNotify,
  ]);

  const streamActive = enabled && connected && pageVisible;

  useEffect(() => {
    if (streamActive) return;
    clearRetryTimer();
    retryCountRef.current = 0;
    failureNotifiedRef.current = false;
    setStreamFailed(false);
  }, [
    clearRetryTimer,
    streamActive,
  ]);

  useEffect(() => {
    if (!calibrated) {
      setUndistortionEnabled(false);
    }
  }, [calibrated]);

  useEffect(() => {
    if (
      meteringRegionEditingRef.current
      || meteringRegionSavingRef.current
    ) {
      return;
    }
    setEditableMeteringRegion(meteringRegion);
  }, [
    meteringRegion?.height,
    meteringRegion?.width,
    meteringRegion?.x,
    meteringRegion?.y,
  ]);

  useEffect(() => {
    const configuredWidth = Number(width);
    const configuredHeight = Number(height);
    if (configuredWidth <= 0 || configuredHeight <= 0) return;

    setFrameSize((current) => (
      current.width === configuredWidth && current.height === configuredHeight
        ? current
        : {
          width: configuredWidth,
          height: configuredHeight,
        }
    ));
  }, [
    height,
    width,
  ]);

  useEffect(() => {
    const updatePageVisibility = () => {
      setPageVisible(document.visibilityState === "visible");
    };

    updatePageVisibility();
    document.addEventListener("visibilitychange", updatePageVisibility);
    return () => {
      document.removeEventListener("visibilitychange", updatePageVisibility);
    };
  }, []);

  useEffect(() => () => {
    window.clearTimeout(retryTimerRef.current);
  }, []);

  const updateMeteringRegionDraft = useCallback((region) => {
    meteringRegionEditingRef.current = true;
    setEditableMeteringRegion(region);
  }, []);

  const cancelMeteringRegionEdit = useCallback((region) => {
    meteringRegionEditingRef.current = false;
    setEditableMeteringRegion(region || meteringRegion);
  }, [meteringRegion]);

  const commitMeteringRegion = useCallback(async (region) => {
    meteringRegionEditingRef.current = false;
    if (typeof onSaveMeteringRegion !== "function") return;

    meteringRegionSavingRef.current = true;
    setMeteringRegionSaving(true);
    try {
      const result = await onSaveMeteringRegion(
        cameraId,
        region,
      );
      setEditableMeteringRegion(
        result?.metering_region || region,
      );
    } catch (error) {
      setEditableMeteringRegion(meteringRegion);
      onNotify?.(
        messageFromError(
          error,
          `${label}測光區域儲存失敗。`,
        ),
        "error",
      );
    } finally {
      meteringRegionSavingRef.current = false;
      setMeteringRegionSaving(false);
    }
  }, [
    cameraId,
    label,
    meteringRegion,
    onNotify,
    onSaveMeteringRegion,
  ]);

  const source = streamPath
    || `/api/cameras/${encodeURIComponent(cameraId)}/stream`;
  const separator = source.includes("?") ? "&" : "?";
  const streamParameters = new URLSearchParams({
    retry: String(retryToken),
  });
  if (calibrated && undistortionEnabled) {
    streamParameters.set("undistort", "true");
  }
  const streamSource = `${source}${separator}${streamParameters.toString()}`;
  const undistortionTitle = !calibrated
    ? "尚無有效內參，無法套用去畸變"
    : undistortionEnabled
      ? "顯示原始影像"
      : "套用即時去畸變";
  const crosshairTitle = crosshairVisible
    ? "隱藏中心十字"
    : "顯示中心十字";
  const exposureTitle = exposureVisible
    ? "隱藏測光輔助框"
    : "顯示並調整測光輔助框";
  const exposureEditable = Boolean(
    exposureVisible
    && onSaveMeteringRegion
    && !meteringRegionDisabled
    && !meteringRegionSaving,
  );

  return (
    <div className="relative min-h-0 overflow-hidden bg-black/35 p-2">
      {streamActive ? (
        <div className="relative aspect-video w-full rounded-2xl bg-black/40">
          {/* 原生 img 才能維持後端 MJPEG 串流連線。 */}
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            className="block size-full rounded-2xl object-contain"
            src={streamSource}
            alt={`${label} 即時預覽`}
            onLoad={handleStreamLoad}
            onError={handleStreamError}
          />
          <CameraGuideOverlay
            cameraId={cameraId}
            crosshairVisible={crosshairVisible}
            exposureVisible={exposureVisible}
            frameWidth={frameSize.width}
            frameHeight={frameSize.height}
            meteringRegion={editableMeteringRegion}
            overexposedRegions={overexposedRegions}
            exposureEditable={exposureEditable}
            onMeteringRegionChange={updateMeteringRegionDraft}
            onMeteringRegionCommit={commitMeteringRegion}
            onMeteringRegionCancel={cancelMeteringRegionEdit}
          />
        </div>
      ) : (
        <div className="grid aspect-video w-full place-items-center rounded-2xl bg-black/40 p-4 text-center text-sm font-bold text-neutral-400">
          {enabled ? "等待相機連線…" : "相機未啟用"}
        </div>
      )}
      <span
        className="absolute top-2 left-1/2 z-10 max-w-[calc(100%_-_4rem)] -translate-x-1/2 overflow-hidden rounded-t-none rounded-b-xl border border-white/15 bg-[#07130f]/80 px-4 py-2 text-center text-sm font-black text-white text-ellipsis whitespace-nowrap shadow-lg backdrop-blur-xl"
        title={device}
      >
        {label}
      </span>
      <div className="absolute bottom-4 left-4 z-10 flex items-center gap-2 max-[420px]:bottom-16">
        <span className="rounded-lg border border-white/15 bg-[#07130f]/80 px-2.5 py-1 text-xs font-black text-white shadow-lg backdrop-blur-xl">
          FPS: {formatFps(actualFps)}
        </span>
        {exposureVisible ? (
          <span className="rounded-lg border border-white/15 bg-[#07130f]/80 px-2.5 py-1 text-xs font-black text-white shadow-lg backdrop-blur-xl">
            曝光: {formatExposure(exposureValue)}
          </span>
        ) : null}
      </div>
      {streamFailed ? (
        <div className="absolute inset-2 z-20 grid place-items-center rounded-2xl bg-[#07130f]/90 p-4 text-center backdrop-blur-xl">
          <div className="grid justify-items-center gap-3">
            <p className="m-0 text-sm font-semibold text-rose-200">
              {retryScheduled
                ? "影像載入失敗，準備重新載入…"
                : "影像串流無法載入。"
              }
            </p>
            <Button
              className="min-h-9 px-3 text-xs"
              onClick={reloadStream}
            >
              <FiRefreshCw
                className="size-3.5 shrink-0"
                aria-hidden="true"
              />
              立即重新載入
            </Button>
          </div>
        </div>
      ) : null}
      {streamActive ? (
        <>
          <Button
            className="absolute right-40 bottom-4 z-30 size-10 min-h-10 shrink-0 p-0! shadow-lg backdrop-blur-xl"
            variant={crosshairVisible ? "primary" : "default"}
            aria-label={crosshairTitle}
            aria-pressed={crosshairVisible}
            title={crosshairTitle}
            onClick={() => setCrosshairVisible((current) => !current)}
          >
            <PiCrosshairBold
              className="size-6 shrink-0"
              aria-hidden="true"
            />
          </Button>
          <Button
            className="absolute right-28 bottom-4 z-30 size-10 min-h-10 shrink-0 p-0! shadow-lg backdrop-blur-xl"
            variant={exposureVisible ? "primary" : "default"}
            aria-label={exposureTitle}
            aria-pressed={exposureVisible}
            title={exposureTitle}
            onClick={() => setExposureVisible((current) => !current)}
          >
            <PiRectangleDashedBold
              className="size-6 shrink-0"
              aria-hidden="true"
            />
          </Button>
          <Button
            className="absolute right-16 bottom-4 z-30 size-10 min-h-10 shrink-0 p-0! shadow-lg backdrop-blur-xl"
            variant={undistortionEnabled ? "primary" : "default"}
            disabled={!calibrated}
            aria-label={undistortionTitle}
            aria-pressed={undistortionEnabled}
            title={undistortionTitle}
            onClick={() => {
              clearRetryTimer();
              retryCountRef.current = 0;
              failureNotifiedRef.current = false;
              setStreamFailed(false);
              setUndistortionEnabled((current) => !current);
            }}
          >
            <FiAperture
              className="size-6 shrink-0"
              aria-hidden="true"
            />
          </Button>
          <FullscreenImage
            label={label}
            src={streamSource}
            alt={`${label}全螢幕即時預覽`}
            onLoad={handleStreamLoad}
            onError={handleStreamError}
          >
            <CameraGuideOverlay
              cameraId={cameraId}
              crosshairVisible={crosshairVisible}
              exposureVisible={exposureVisible}
              frameWidth={frameSize.width}
              frameHeight={frameSize.height}
              meteringRegion={editableMeteringRegion}
              overexposedRegions={overexposedRegions}
              exposureEditable={exposureEditable}
              onMeteringRegionChange={updateMeteringRegionDraft}
              onMeteringRegionCommit={commitMeteringRegion}
              onMeteringRegionCancel={cancelMeteringRegionEdit}
            />
            {streamFailed ? (
              <div className="absolute inset-0 z-20 grid place-items-center rounded-2xl bg-[#07130f]/90 p-4 text-center backdrop-blur-xl">
                <div className="grid justify-items-center gap-3">
                  <p className="m-0 text-sm font-semibold text-rose-200">
                    {retryScheduled
                      ? "影像載入失敗，準備重新載入…"
                      : "影像串流無法載入。"
                    }
                  </p>
                  <Button
                    className="min-h-9 px-3 text-xs"
                    onClick={reloadStream}
                  >
                    <FiRefreshCw
                      className="size-3.5 shrink-0"
                      aria-hidden="true"
                    />
                    立即重新載入
                  </Button>
                </div>
              </div>
            ) : null}
          </FullscreenImage>
        </>
      ) : null}
    </div>
  );
}

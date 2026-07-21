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

import Button from "@/components/buttons/Button";
import FullscreenImage from "@/components/media/FullscreenImage";

const RETRY_DELAYS_MS = [1500, 3000, 5000];

function formatFps(value) {
  const fps = Number(value);
  return Number.isFinite(fps) && fps > 0
    ? String(Math.round(fps))
    : "0";
}

export default function CameraStream({
  cameraId,
  label,
  device,
  enabled,
  connected,
  actualFps,
  calibrated = false,
  streamPath,
  onNotify,
}) {
  const [retryToken, setRetryToken] = useState(0);
  const [streamFailed, setStreamFailed] = useState(false);
  const [retryScheduled, setRetryScheduled] = useState(false);
  const [pageVisible, setPageVisible] = useState(true);
  const [undistortionEnabled, setUndistortionEnabled] = useState(false);
  const retryTimerRef = useRef(null);
  const retryCountRef = useRef(0);
  const failureNotifiedRef = useRef(false);

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

  const handleStreamLoad = useCallback(() => {
    if (!enabled) return;
    clearRetryTimer();
    retryCountRef.current = 0;
    failureNotifiedRef.current = false;
    setStreamFailed(false);
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

  return (
    <div className="relative min-h-0 overflow-hidden bg-black/35 p-2">
      {streamActive ? (
        <img
          className="block aspect-video w-full rounded-2xl bg-black/40 object-contain"
          src={streamSource}
          alt={`${label} 即時預覽`}
          onLoad={handleStreamLoad}
          onError={handleStreamError}
        />
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
      <span className="absolute bottom-4 left-4 z-10 rounded-lg border border-white/15 bg-[#07130f]/80 px-2.5 py-1 text-xs font-black text-white shadow-lg backdrop-blur-xl">
        FPS: {formatFps(actualFps)}
      </span>
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

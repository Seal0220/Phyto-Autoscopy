"use client";

import {
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";
import { FiRefreshCw } from "react-icons/fi";

import Button from "@/components/buttons/Button";

import ImagePreviewFullscreen from "./ImagePreviewFullscreen";

const RETRY_DELAYS_MS = [1500, 3000, 5000];

export default function ImagePreviewFeed({
  imagePreviewId,
  label,
  device,
  enabled,
  connected,
  reconnectPending,
  onNotify,
}) {
  const [retryToken, setRetryToken] = useState(0);
  const [streamFailed, setStreamFailed] = useState(false);
  const [retryScheduled, setRetryScheduled] = useState(false);
  const retryTimerRef = useRef(null);
  const retryCountRef = useRef(0);
  const failureNotifiedRef = useRef(false);
  const previousConnectedRef = useRef(connected);
  const previousReconnectPendingRef = useRef(reconnectPending);

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

  useEffect(() => {
    if (enabled) {
      reloadStream();
      return;
    }

    clearRetryTimer();
    retryCountRef.current = 0;
    failureNotifiedRef.current = false;
    setStreamFailed(false);
  }, [
    clearRetryTimer,
    enabled,
    reloadStream,
  ]);

  useEffect(() => {
    const wasConnected = previousConnectedRef.current;
    previousConnectedRef.current = connected;

    if (enabled && !wasConnected && connected) {
      reloadStream();
    }
  }, [
    connected,
    enabled,
    reloadStream,
  ]);

  useEffect(() => {
    const wasReconnectPending = previousReconnectPendingRef.current;
    previousReconnectPendingRef.current = reconnectPending;

    if (enabled && wasReconnectPending && !reconnectPending) {
      reloadStream();
    }
  }, [
    enabled,
    reconnectPending,
    reloadStream,
  ]);

  useEffect(() => () => {
    window.clearTimeout(retryTimerRef.current);
  }, []);

  const streamSource = `/api/cameras/${encodeURIComponent(imagePreviewId)}/stream?retry=${retryToken}`;

  return (
    <div className="relative min-h-0 overflow-hidden bg-black/35 p-2">
      {enabled ? (
        <img
          className="block aspect-4/3 w-full rounded-2xl bg-black/40 object-cover"
          src={streamSource}
          alt={`${label} 即時預覽`}
          onLoad={handleStreamLoad}
          onError={handleStreamError}
        />
      ) : (
        <div className="grid aspect-4/3 w-full place-items-center rounded-2xl bg-black/40 p-4 text-center text-sm font-bold text-neutral-400">
          相機未啟用
        </div>
      )}
      <span
        className="absolute top-2 left-1/2 z-10 max-w-[calc(100%_-_4rem)] -translate-x-1/2 overflow-hidden rounded-t-none rounded-b-xl border border-white/15 bg-[#07130f]/80 px-4 py-2 text-center text-sm font-black text-white text-ellipsis whitespace-nowrap shadow-lg backdrop-blur-xl"
        title={device}
      >
        {label}
      </span>
      {streamFailed ? (
        <div className="absolute inset-2 z-20 grid place-items-center rounded-2xl bg-[#07130f]/90 p-4 text-center backdrop-blur-xl">
          <div className="grid justify-items-center gap-3">
            <p className="m-0 text-sm font-semibold text-rose-200">
              {retryScheduled ? "影像載入失敗，準備重新載入…" : "影像串流無法載入。"}
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
      {enabled ? (
        <ImagePreviewFullscreen
          label={label}
          streamSource={streamSource}
          streamFailed={streamFailed}
          retryScheduled={retryScheduled}
          onStreamLoad={handleStreamLoad}
          onStreamError={handleStreamError}
          onRetry={reloadStream}
        />
      ) : null}
    </div>
  );
}

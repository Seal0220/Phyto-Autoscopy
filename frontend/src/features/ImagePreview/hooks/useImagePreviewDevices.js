"use client";

import {
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";

import {
  abortRequest,
  RequestTimeoutError,
  messageFromError,
  parseJsonResponse,
  responseErrorMessage,
  withRequestTimeout,
} from "@/lib/httpUtils";
import { CAMERA_GROUP_ACTION_TIMEOUT_MS } from "@/lib/proxyTimeoutUtils";

const DEVICE_SCAN_TIMEOUT_MS = CAMERA_GROUP_ACTION_TIMEOUT_MS + 5_000;

export default function useImagePreviewDevices({
  open,
  onNotify,
}) {
  const [scanResults, setScanResults] = useState([]);
  const [scanning, setScanning] = useState(false);
  const mountedRef = useRef(false);
  const scanningRef = useRef(false);
  const scannedRef = useRef(false);
  const abortRef = useRef(null);

  useEffect(() => {
    mountedRef.current = true;

    return () => {
      mountedRef.current = false;
      scanningRef.current = false;
      scannedRef.current = false;
      abortRequest(abortRef.current);
      abortRef.current = null;
    };
  }, []);

  const scanDevices = useCallback(async () => {
    if (scanningRef.current) return false;

    const controller = new AbortController();
    scanningRef.current = true;
    abortRef.current = controller;
    setScanning(true);

    try {
      const {
        response,
        result,
      } = await withRequestTimeout(
        async (signal) => {
          const response = await fetch("/api/cameras/scan", {
            cache: "no-store",
            signal,
          });
          const result = await parseJsonResponse(response);

          return {
            response,
            result,
          };
        },
        {
          signal: controller.signal,
          timeoutMs: DEVICE_SCAN_TIMEOUT_MS,
        },
      );

      if (!response.ok) {
        throw new Error(responseErrorMessage(
          result,
          "掃描相機裝置失敗。",
        ));
      }

      if (!Array.isArray(result)) {
        throw new Error("相機裝置資料格式錯誤，請重新掃描。");
      }

      if (!mountedRef.current || controller.signal.aborted) return false;

      setScanResults(result);
      return true;
    } catch (error) {
      if (error?.name === "AbortError") return false;

      if (mountedRef.current) {
        const message = error instanceof RequestTimeoutError
          ? "掃描相機裝置逾時，請確認裝置連線後重試。"
          : messageFromError(error, "掃描相機裝置失敗。");

        onNotify?.(
          message,
          "error",
        );
      }

      return false;
    } finally {
      if (abortRef.current === controller) {
        abortRef.current = null;
        scanningRef.current = false;

        if (mountedRef.current) {
          setScanning(false);
        }
      }
    }
  }, [onNotify]);

  useEffect(() => {
    if (!open || scannedRef.current) return;
    scannedRef.current = true;
    void scanDevices();
  }, [
    open,
    scanDevices,
  ]);

  return {
    scanResults,
    scanning,
    scanDevices,
  };
}

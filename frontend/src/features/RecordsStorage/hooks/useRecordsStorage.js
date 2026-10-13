"use client";

import {
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";

import {
  abortRequest,
  messageFromError,
  parseJsonResponse,
  responseErrorMessage,
} from "@/lib/httpUtils";
import { usePageDataCache } from "@/hooks/PageDataCacheProvider";

export default function useRecordsStorage({
  onNotify,
}) {
  const cache = usePageDataCache();
  const cacheKey = "records:list";
  const [records, setRecords] = useState(() => cache.read(cacheKey)?.value || []);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState("");
  const loadingRef = useRef(false);
  const mountedRef = useRef(false);
  const loadAbortRef = useRef(null);
  const reloadRequestedRef = useRef(false);
  const reloadTimerRef = useRef(null);

  useEffect(() => {
    mountedRef.current = true;

    return () => {
      const loadController = loadAbortRef.current;

      mountedRef.current = false;
      loadingRef.current = false;
      loadAbortRef.current = null;
      reloadRequestedRef.current = false;
      window.clearTimeout(reloadTimerRef.current);
      abortRequest(loadController);
    };
  }, []);

  const loadRecords = useCallback(async ({
    queueIfBusy = false,
    preferCache = false,
  } = {}) => {
    if (loadingRef.current) {
      if (queueIfBusy) {
        reloadRequestedRef.current = true;
      }

      return false;
    }
    const cached = cache.read(cacheKey);
    if (preferCache && cached?.fresh) return true;

    const controller = new AbortController();
    const cacheVersion = cache.version;
    loadingRef.current = true;
    loadAbortRef.current = controller;
    if (!(preferCache && cached)) setLoading(true);
    setLoadError("");

    try {
      const response = await fetch("/api/records", {
        cache: "no-store",
        signal: controller.signal,
      });
      const payload = await parseJsonResponse(response);

      if (!response.ok) {
        throw new Error(responseErrorMessage(
          payload,
          "讀取紀錄失敗。",
        ));
      }

      if (!Array.isArray(payload)) {
        throw new Error("紀錄資料格式錯誤，請重新讀取。");
      }

      if (!mountedRef.current || controller.signal.aborted) return false;

      setRecords(payload);
      cache.write(
        cacheKey,
        payload,
        cacheVersion,
      );
      setLoadError("");
      return true;
    } catch (error) {
      if (error?.name === "AbortError") return false;

      const message = messageFromError(error, "讀取紀錄失敗。");

      if (!mountedRef.current) return false;

      setLoadError(message);
      onNotify?.(message, "error");
      return false;
    } finally {
      if (loadAbortRef.current === controller) {
        loadAbortRef.current = null;
        loadingRef.current = false;

        if (mountedRef.current) {
          setLoading(false);
        }

        if (reloadRequestedRef.current && mountedRef.current) {
          reloadRequestedRef.current = false;
          window.clearTimeout(reloadTimerRef.current);
          reloadTimerRef.current = window.setTimeout(() => {
            reloadTimerRef.current = null;

            if (mountedRef.current) {
              void loadRecords();
            }
          }, 0);
        }
      }
    }
  }, [cache, onNotify]);

  useEffect(() => {
    void loadRecords({ preferCache: true });
  }, [loadRecords]);

  return {
    records,
    loading,
    loadError,
    loadRecords,
  };
}

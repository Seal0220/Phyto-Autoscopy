"use client";

import {
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";

import {
  cloneValue,
  serializeSettingsPayload,
  setNestedValue,
} from "@/features/Settings/lib/settingsUtils";
import {
  abortRequest,
  RequestTimeoutError,
  messageFromError,
  parseJsonResponse,
  responseErrorMessage,
  withRequestTimeout,
} from "@/lib/httpUtils";

export default function useSettings({
  group,
  onNotify,
  open,
  serializePayload,
}) {
  const [payload, setPayload] = useState(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [loadFailed, setLoadFailed] = useState(false);
  const [loadError, setLoadError] = useState("");
  const hasLoadedRef = useRef(false);
  const loadingRef = useRef(false);
  const savingRef = useRef(false);
  const mountedRef = useRef(false);
  const loadAbortRef = useRef(null);
  const saveAbortRef = useRef(null);

  useEffect(() => {
    mountedRef.current = true;

    return () => {
      const loadController = loadAbortRef.current;
      const saveController = saveAbortRef.current;

      mountedRef.current = false;
      hasLoadedRef.current = false;
      loadingRef.current = false;
      savingRef.current = false;
      loadAbortRef.current = null;
      saveAbortRef.current = null;
      abortRequest(loadController);
      abortRequest(saveController);
    };
  }, []);

  useEffect(() => {
    const loadController = loadAbortRef.current;
    const saveController = saveAbortRef.current;

    hasLoadedRef.current = false;
    loadingRef.current = false;
    savingRef.current = false;
    loadAbortRef.current = null;
    saveAbortRef.current = null;
    abortRequest(loadController);
    abortRequest(saveController);
    setPayload(null);
    setLoading(false);
    setSaving(false);
    setLoadFailed(false);
    setLoadError("");
  }, [group]);

  const loadGroup = useCallback(async () => {
    if (loadingRef.current) return false;

    const controller = new AbortController();
    loadingRef.current = true;
    loadAbortRef.current = controller;
    setLoading(true);
    setLoadFailed(false);
    setLoadError("");

    try {
      const {
        response,
        nextPayload,
      } = await withRequestTimeout(
        async (signal) => {
          const response = await fetch(`/api/settings/${group}`, {
            cache: "no-store",
            signal,
          });
          const nextPayload = await parseJsonResponse(response);

          return {
            response,
            nextPayload,
          };
        },
        {
          signal: controller.signal,
        },
      );

      if (!response.ok) {
        throw new Error(responseErrorMessage(
          nextPayload,
          "讀取設定失敗。",
        ));
      }

      if (
        !nextPayload
        || typeof nextPayload !== "object"
        || Array.isArray(nextPayload)
        || Object.keys(nextPayload).length === 0
      ) {
        throw new Error("設定資料格式錯誤，請重新讀取。");
      }

      if (!mountedRef.current || controller.signal.aborted) return false;

      setPayload(cloneValue(nextPayload));
      setLoadFailed(false);
      setLoadError("");
      return true;
    } catch (error) {
      if (error?.name === "AbortError") {
        return false;
      }

      const message = error instanceof RequestTimeoutError
        ? "讀取設定逾時，請重新讀取。"
        : messageFromError(error, "讀取設定失敗。");

      if (!mountedRef.current) return false;

      setLoadFailed(true);
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
      }
    }
  }, [group, onNotify]);

  useEffect(() => {
    if (!open || hasLoadedRef.current) return;
    hasLoadedRef.current = true;
    void loadGroup();
  }, [loadGroup, open]);

  const updateField = useCallback(
    (
      path,
      value,
    ) => {
      setPayload((previous) => {
        if (!previous) return previous;
        const nextPayload = cloneValue(previous);
        setNestedValue(nextPayload, path, value);
        return nextPayload;
      });
    },
    [],
  );

  async function saveGroup() {
    if (!payload || savingRef.current) return false;

    const controller = new AbortController();
    let requestStarted = false;
    let responseReceived = false;
    let outcomeUnknown = false;
    savingRef.current = true;
    saveAbortRef.current = controller;
    setSaving(true);

    try {
      const nextPayload = serializePayload
        ? serializePayload(payload)
        : serializeSettingsPayload(group, payload);
      requestStarted = true;
      const {
        response,
        result,
      } = await withRequestTimeout(
        async (signal) => {
          const response = await fetch(`/api/settings/${group}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ payload: nextPayload }),
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
        },
      );
      responseReceived = true;

      if (!response.ok) {
        outcomeUnknown = response.status >= 500 || response.status === 408;
        throw new Error(responseErrorMessage(
          result,
          "儲存設定失敗。",
        ));
      }

      if (result?.updated !== group || result?.applied !== true) {
        outcomeUnknown = true;
        throw new Error("儲存設定的回應格式錯誤，請重新讀取確認。");
      }

      if (!mountedRef.current || controller.signal.aborted) return false;

      setPayload(nextPayload);
      onNotify?.("已儲存並立即套用。", "success");
      return true;
    } catch (error) {
      if (error?.name === "AbortError") {
        return false;
      }

      if (mountedRef.current) {
        outcomeUnknown = outcomeUnknown
          || error instanceof RequestTimeoutError
          || (requestStarted && !responseReceived);
        const message = outcomeUnknown
          ? "儲存結果尚未確認，請重新讀取設定後再操作。"
          : messageFromError(error, "儲存設定失敗。");

        if (outcomeUnknown) {
          hasLoadedRef.current = false;
          setPayload(null);
          setLoadFailed(true);
          setLoadError(message);
        }

        onNotify?.(message, "error");
      }

      return false;
    } finally {
      if (saveAbortRef.current === controller) {
        saveAbortRef.current = null;
        savingRef.current = false;

        if (mountedRef.current) {
          setSaving(false);
        }
      }
    }
  }

  return {
    payload,
    loading,
    saving,
    loadFailed,
    loadError,
    loadGroup,
    updateField,
    saveGroup,
  };
}

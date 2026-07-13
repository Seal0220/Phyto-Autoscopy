"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import {
  cloneValue,
  serializeSettingsPayload,
  setNestedValue,
} from "@/features/Settings/lib/settingsUtils";
import {
  messageFromError,
  parseJsonResponse,
  responseErrorMessage,
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
      loadController?.abort();
      saveController?.abort();
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
    loadController?.abort();
    saveController?.abort();
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
      const response = await fetch(`/api/settings/${group}`, {
        cache: "no-store",
        signal: controller.signal,
      });
      const nextPayload = await parseJsonResponse(response);

      if (!response.ok) {
        throw new Error(responseErrorMessage(
          nextPayload,
          "讀取設定失敗。",
        ));
      }

      if (!nextPayload || typeof nextPayload !== "object" || Array.isArray(nextPayload)) {
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

      const message = messageFromError(error, "讀取設定失敗。");

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

  function updateField(
    path,
    value,
  ) {
    setPayload((previous) => {
      if (!previous) return previous;
      const nextPayload = cloneValue(previous);
      setNestedValue(nextPayload, path, value);
      return nextPayload;
    });
  }

  async function saveGroup() {
    if (!payload || savingRef.current) return false;

    const controller = new AbortController();
    savingRef.current = true;
    saveAbortRef.current = controller;
    setSaving(true);

    try {
      const nextPayload = serializePayload
        ? serializePayload(payload)
        : serializeSettingsPayload(group, payload);
      const response = await fetch(`/api/settings/${group}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ payload: nextPayload }),
        signal: controller.signal,
      });
      const result = await parseJsonResponse(response);

      if (!response.ok) {
        throw new Error(responseErrorMessage(
          result,
          "儲存設定失敗。",
        ));
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
        onNotify?.(messageFromError(error, "儲存設定失敗。"), "error");
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

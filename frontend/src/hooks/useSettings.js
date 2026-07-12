"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import {
  cloneValue,
  serializeSettingsPayload,
  setNestedValue,
} from "@/features/Settings/lib/settingsUtils";

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
  const hasLoadedRef = useRef(false);

  const loadGroup = useCallback(async () => {
    setLoading(true);
    setLoadFailed(false);
    try {
      const response = await fetch(`/api/settings/${group}`, { cache: "no-store" });
      const nextPayload = await response.json();
      if (!response.ok) throw new Error(nextPayload.detail || "讀取設定失敗。");
      setPayload(cloneValue(nextPayload));
    } catch (error) {
      setLoadFailed(true);
      onNotify?.(error.message || "讀取設定失敗。", "error");
    } finally {
      setLoading(false);
    }
  }, [group, onNotify]);

  useEffect(() => {
    if (!open || hasLoadedRef.current) return;
    hasLoadedRef.current = true;
    void loadGroup();
  }, [loadGroup, open]);

  function updateField(path, value) {
    setPayload((previous) => {
      if (!previous) return previous;
      const nextPayload = cloneValue(previous);
      setNestedValue(nextPayload, path, value);
      return nextPayload;
    });
  }

  async function saveGroup() {
    if (!payload) return;
    setSaving(true);
    try {
      const nextPayload = serializePayload
        ? serializePayload(payload)
        : serializeSettingsPayload(group, payload);
      const response = await fetch(`/api/settings/${group}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ payload: nextPayload }),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail || "儲存設定失敗。");
      setPayload(nextPayload);
      onNotify?.("已儲存並立即套用。", "success");
    } catch (error) {
      onNotify?.(error.message || "儲存設定失敗。", "error");
    } finally {
      setSaving(false);
    }
  }

  return { payload, loading, saving, loadFailed, updateField, saveGroup };
}

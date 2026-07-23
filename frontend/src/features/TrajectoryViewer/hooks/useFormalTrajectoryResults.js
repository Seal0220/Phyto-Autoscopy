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
} from "@/lib/httpUtils";

import {
  downloadFormalTrajectoryExport,
  loadFormalTrajectoryResults,
} from "../lib/formalTrajectoryApiUtils";

const EMPTY_DATA = {
  run: null,
  rounds: [],
  models: [],
  landmarks: [],
  corrections: [],
  trajectory: [],
  quality: {},
};

export default function useFormalTrajectoryResults({
  analysisId,
}) {
  const [data, setData] = useState(EMPTY_DATA);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [exportPending, setExportPending] = useState(false);
  const [exportError, setExportError] = useState("");
  const mountedRef = useRef(false);
  const loadControllerRef = useRef(null);
  const exportControllerRef = useRef(null);

  const load = useCallback(async () => {
    abortRequest(
      loadControllerRef.current,
      "已由新的正式分析結果讀取取代。",
    );
    const controller = new AbortController();
    loadControllerRef.current = controller;
    setLoading(true);
    setLoadError("");
    try {
      const payload = await loadFormalTrajectoryResults(
        analysisId,
        controller.signal,
      );
      if (mountedRef.current) setData(payload);
    } catch (error) {
      if (error?.name !== "AbortError" && mountedRef.current) {
        setLoadError(messageFromError(
          error,
          "讀取每輪模型與尖端標記軌跡失敗。",
        ));
      }
    } finally {
      if (loadControllerRef.current === controller) {
        loadControllerRef.current = null;
      }
      if (mountedRef.current) setLoading(false);
    }
  }, [analysisId]);

  useEffect(() => {
    mountedRef.current = true;
    void load();
    return () => {
      mountedRef.current = false;
      abortRequest(loadControllerRef.current, "分析結果頁面已關閉。");
      abortRequest(exportControllerRef.current, "分析結果頁面已關閉。");
    };
  }, [load]);

  const downloadExport = useCallback(async () => {
    if (exportControllerRef.current) return;
    const controller = new AbortController();
    exportControllerRef.current = controller;
    setExportPending(true);
    setExportError("");
    try {
      const { blob, filename } = await downloadFormalTrajectoryExport(
        analysisId,
        controller.signal,
      );
      if (!(blob instanceof Blob) || blob.size === 0) {
        throw new Error("分析匯出檔沒有內容。");
      }
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = filename;
      anchor.hidden = true;
      document.body.append(anchor);
      anchor.click();
      anchor.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 1_000);
    } catch (error) {
      if (error?.name !== "AbortError" && mountedRef.current) {
        setExportError(messageFromError(
          error,
          "下載分析匯出檔失敗。",
        ));
      }
    } finally {
      if (exportControllerRef.current === controller) {
        exportControllerRef.current = null;
      }
      if (mountedRef.current) setExportPending(false);
    }
  }, [analysisId]);

  return {
    ...data,
    loading,
    loadError,
    exportPending,
    exportError,
    load,
    downloadExport,
    clearExportError: () => setExportError(""),
  };
}

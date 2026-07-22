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
  RequestTimeoutError,
} from "@/lib/httpUtils";
import { downloadAnalysisExport } from "@/features/AnalysisRun/lib/analysisRunApiUtils";
import { usePhytoSocketContext } from "@/hooks/PhytoSocketProvider";

import { loadAnalysisDashboard } from "../lib/analysisApiUtils";
import {
  analysisRunsFromPayload,
  analysisSourcesFromPayload,
  mergeAnalysisProgress,
  mergeAnalysisRuns,
} from "../lib/analysisUtils";

const POLLING_STATUSES = new Set([
  "validating",
  "processing",
  "reconstructing",
]);
const ACTIVE_POLL_INTERVAL_MS = 5_000;

export default function useAnalysisDashboard() {
  const [sources, setSources] = useState([]);
  const [runs, setRuns] = useState([]);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState("");
  const [exportingIds, setExportingIds] = useState(() => new Set());
  const [exportFailure, setExportFailure] = useState(null);
  const mountedRef = useRef(false);
  const loadingRef = useRef(false);
  const controllerRef = useRef(null);
  const exportControllersRef = useRef(new Map());
  const {
    snapshot,
    connection,
    socketError,
    resetSocketError,
  } = usePhytoSocketContext();

  useEffect(() => {
    mountedRef.current = true;

    return () => {
      mountedRef.current = false;
      loadingRef.current = false;
      abortRequest(controllerRef.current);
      controllerRef.current = null;
      for (const controller of exportControllersRef.current.values()) {
        abortRequest(controller);
      }
      exportControllersRef.current.clear();
    };
  }, []);

  const load = useCallback(async () => {
    if (loadingRef.current) return false;

    const controller = new AbortController();
    controllerRef.current = controller;
    loadingRef.current = true;
    setLoading(true);

    try {
      const [sourcePayload, runPayload] = await loadAnalysisDashboard(
        controller.signal,
      );
      const nextSources = analysisSourcesFromPayload(sourcePayload);
      const nextRuns = mergeAnalysisRuns(
        nextSources,
        analysisRunsFromPayload(runPayload),
      );

      if (!mountedRef.current || controller.signal.aborted) return false;

      setSources(nextSources);
      setRuns(nextRuns);
      setLoadError("");
      return true;
    } catch (error) {
      if (error?.name === "AbortError") return false;

      const fallback = error instanceof RequestTimeoutError
        ? "讀取分析資料逾時，請重新讀取。"
        : "讀取分析資料失敗。";

      if (mountedRef.current) {
        setLoadError(messageFromError(
          error,
          fallback,
        ));
      }
      return false;
    } finally {
      if (controllerRef.current === controller) {
        controllerRef.current = null;
        loadingRef.current = false;

        if (mountedRef.current) setLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (!snapshot?.analysis) return;
    setRuns((current) => mergeAnalysisProgress(
      current,
      snapshot.analysis,
    ));
  }, [snapshot]);

  const hasPollingRun = runs.some((run) => POLLING_STATUSES.has(run.status));

  useEffect(() => {
    if (!hasPollingRun) return undefined;

    function refreshVisibleRun() {
      if (document.visibilityState === "visible") {
        void load();
      }
    }

    const intervalId = window.setInterval(
      refreshVisibleRun,
      ACTIVE_POLL_INTERVAL_MS,
    );
    document.addEventListener(
      "visibilitychange",
      refreshVisibleRun,
    );

    return () => {
      window.clearInterval(intervalId);
      document.removeEventListener(
        "visibilitychange",
        refreshVisibleRun,
      );
    };
  }, [
    hasPollingRun,
    load,
  ]);

  const exportRun = useCallback(async (analysisId) => {
    if (!analysisId || exportControllersRef.current.has(analysisId)) {
      return false;
    }

    const controller = new AbortController();
    exportControllersRef.current.set(
      analysisId,
      controller,
    );
    setExportingIds((current) => {
      const next = new Set(current);
      next.add(analysisId);
      return next;
    });
    setExportFailure((current) => (
      current?.analysisId === analysisId ? null : current
    ));

    try {
      const {
        blob,
        filename,
      } = await downloadAnalysisExport(
        analysisId,
        controller.signal,
      );
      if (!mountedRef.current || controller.signal.aborted) return false;
      if (!(blob instanceof Blob) || blob.size === 0) {
        throw new Error("分析匯出檔沒有內容。");
      }

      const objectUrl = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = objectUrl;
      anchor.download = filename;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      window.setTimeout(() => URL.revokeObjectURL(objectUrl), 0);
      setExportFailure((current) => (
        current?.analysisId === analysisId ? null : current
      ));
      return true;
    } catch (error) {
      if (error?.name === "AbortError") return false;
      if (mountedRef.current) {
        setExportFailure({
          analysisId,
          message: messageFromError(
            error,
            error instanceof RequestTimeoutError
              ? "下載分析匯出檔逾時，請重試。"
              : "下載分析匯出檔失敗。",
          ),
        });
      }
      return false;
    } finally {
      if (exportControllersRef.current.get(analysisId) === controller) {
        exportControllersRef.current.delete(analysisId);
        if (mountedRef.current) {
          setExportingIds((current) => {
            const next = new Set(current);
            next.delete(analysisId);
            return next;
          });
        }
      }
    }
  }, []);

  return {
    sources,
    runs,
    loading,
    loadError,
    exportingIds,
    exportFailure,
    connection,
    socketError,
    load,
    exportRun,
    resetSocketError,
    clearExportFailure: () => setExportFailure(null),
  };
}

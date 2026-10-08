"use client";

import {
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";

import { usePhytoSocketContext } from "@/hooks/PhytoSocketProvider";
import {
  abortRequest,
  messageFromError,
} from "@/lib/httpUtils";

import {
  downloadAnalysisExport,
  loadAnalysisProgress,
  loadAnalysisRunBundle,
  performAnalysisRunAction,
  UnknownAnalysisMutationOutcomeError,
} from "../lib/analysisRunApiUtils";
import {
  normalizeAnalysisProgress,
  normalizeAnalysisRun,
} from "../lib/analysisRunUtils";

const POLL_INTERVAL_MS = 2_500;
const POLLED_STATUSES = new Set([
  "validating",
  "processing",
  "reconstructing",
  "pausing",
]);

export default function useAnalysisRun({
  analysisId,
}) {
  const [run, setRun] = useState(null);
  const [progress, setProgress] = useState(null);
  const [formalData, setFormalData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [pendingAction, setPendingAction] = useState("");
  const [mutationError, setMutationError] = useState("");
  const [mutationOutcomeUnknown, setMutationOutcomeUnknown] = useState(false);
  const [exportPending, setExportPending] = useState(false);
  const [exportError, setExportError] = useState("");
  const mountedRef = useRef(false);
  const loadControllerRef = useRef(null);
  const mutationControllerRef = useRef(null);
  const exportControllerRef = useRef(null);
  const progressControllerRef = useRef(null);
  const loadGenerationRef = useRef(0);
  const pollingRef = useRef(false);
  const runStatusRef = useRef("");
  const lastTerminalProgressRef = useRef("");
  const lastRoundProgressRef = useRef("");
  const {
    snapshot,
    socketError,
    resetSocketError,
  } = usePhytoSocketContext();

  const load = useCallback(async ({
    silent = false,
    confirmMutation = false,
  } = {}) => {
    const generation = loadGenerationRef.current + 1;
    loadGenerationRef.current = generation;
    abortRequest(
      loadControllerRef.current,
      "已由新的分析紀錄讀取取代。",
    );
    const controller = new AbortController();
    loadControllerRef.current = controller;

    if (!silent) setLoading(true);
    setLoadError("");

    try {
      const bundle = await loadAnalysisRunBundle(
        analysisId,
        controller.signal,
      );
      if (!mountedRef.current || generation !== loadGenerationRef.current) return false;

      const normalizedRun = normalizeAnalysisRun(bundle.run);
      runStatusRef.current = normalizedRun.status;
      setRun(normalizedRun);
      setProgress(normalizeAnalysisProgress(bundle.progress));
      setFormalData(bundle.formalData);
      setLoadError("");
      if (confirmMutation) {
        setMutationOutcomeUnknown(false);
        setMutationError("");
      }
      return true;
    } catch (error) {
      if (error?.name === "AbortError") return false;
      if (mountedRef.current && generation === loadGenerationRef.current) {
        setLoadError(messageFromError(
          error,
          "讀取分析紀錄狀態失敗。",
        ));
      }
      return false;
    } finally {
      if (loadControllerRef.current === controller) {
        loadControllerRef.current = null;
      }
      if (mountedRef.current && generation === loadGenerationRef.current && !silent) {
        setLoading(false);
      }
    }
  }, [analysisId]);

  const applyProgress = useCallback((payload) => {
    const next = normalizeAnalysisProgress(payload);
    if (!mountedRef.current || next.analysis_id !== analysisId) return;
    runStatusRef.current = next.status;
    setProgress(next);
    if (!POLLED_STATUSES.has(next.status)) {
      const terminalKey = `${analysisId}:${next.status}`;
      if (lastTerminalProgressRef.current !== terminalKey) {
        lastTerminalProgressRef.current = terminalKey;
        void load({ silent: true });
      }
    } else {
      lastTerminalProgressRef.current = "";
      const roundKey = next.round_key
        ? `${next.round_key}:${next.round_progress === 1 ? "completed" : "processing"}`
        : "";
      if (roundKey && lastRoundProgressRef.current !== roundKey) {
        lastRoundProgressRef.current = roundKey;
        void load({ silent: true });
      }
    }
  }, [analysisId, load]);

  const pollProgress = useCallback(async () => {
    const controller = new AbortController();
    const generation = loadGenerationRef.current;
    progressControllerRef.current = controller;
    try {
      const payload = await loadAnalysisProgress(
        analysisId,
        controller.signal,
      );
      if (!mountedRef.current || generation !== loadGenerationRef.current) return;
      setLoadError("");
      applyProgress(payload);
    } catch (error) {
      if (error?.name !== "AbortError" && mountedRef.current
        && generation === loadGenerationRef.current) {
        setLoadError(messageFromError(
          error,
          "讀取分析進度失敗，請重新讀取。",
        ));
      }
    } finally {
      if (progressControllerRef.current === controller) {
        progressControllerRef.current = null;
      }
    }
  }, [analysisId, applyProgress]);

  useEffect(() => {
    mountedRef.current = true;
    void load();

    const interval = window.setInterval(() => {
      if (
        document.visibilityState !== "visible"
        || pollingRef.current
        || loadControllerRef.current
        || !POLLED_STATUSES.has(runStatusRef.current)
      ) {
        return;
      }
      pollingRef.current = true;
      void pollProgress().finally(() => {
        pollingRef.current = false;
      });
    }, POLL_INTERVAL_MS);

    return () => {
      mountedRef.current = false;
      window.clearInterval(interval);
      loadGenerationRef.current += 1;
      abortRequest(loadControllerRef.current);
      abortRequest(mutationControllerRef.current);
      abortRequest(exportControllerRef.current);
      abortRequest(progressControllerRef.current);
    };
  }, [load, pollProgress]);

  useEffect(() => {
    applyProgress(snapshot?.analysis);
  }, [
    applyProgress,
    snapshot,
  ]);

  async function performAction(action) {
    if (
      pendingAction
      || mutationControllerRef.current
      || mutationOutcomeUnknown
    ) {
      return null;
    }

    const controller = new AbortController();
    mutationControllerRef.current = controller;
    setPendingAction(action);
    setMutationError("");

    try {
      const payload = await performAnalysisRunAction(
        analysisId,
        action,
        controller.signal,
      );
      if (!mountedRef.current) return null;

      const nextRun = normalizeAnalysisRun(payload);
      runStatusRef.current = nextRun.status;
      setRun(nextRun);
      setProgress((previous) => normalizeAnalysisProgress({
        ...previous,
        analysis_id: nextRun.analysis_id,
        status: nextRun.status,
        stage: nextRun.stage,
        current_frame: nextRun.current_frame,
        total_frames: nextRun.total_frames,
        progress: nextRun.progress,
        last_error: nextRun.last_error,
      }));
      setMutationError("");
      setMutationOutcomeUnknown(false);
      void load({ silent: true });
      return nextRun;
    } catch (error) {
      if (error?.name === "AbortError") return null;
      if (mountedRef.current) {
        const unknown = error instanceof UnknownAnalysisMutationOutcomeError;
        setMutationOutcomeUnknown(unknown);
        setMutationError(messageFromError(
          error,
          "分析操作失敗，請重新讀取後再試。",
        ));
      }
      return null;
    } finally {
      if (mutationControllerRef.current === controller) {
        mutationControllerRef.current = null;
        if (mountedRef.current) setPendingAction("");
      }
    }
  }

  async function downloadExport() {
    if (exportPending || exportControllerRef.current) return;
    const controller = new AbortController();
    exportControllerRef.current = controller;
    setExportPending(true);
    setExportError("");

    try {
      const { blob, filename } = await downloadAnalysisExport(
        analysisId,
        controller.signal,
      );
      if (!mountedRef.current) return;
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
      setExportError("");
    } catch (error) {
      if (error?.name === "AbortError") return;
      if (mountedRef.current) {
        setExportError(messageFromError(
          error,
          "下載分析匯出檔失敗。",
        ));
      }
    } finally {
      if (exportControllerRef.current === controller) {
        exportControllerRef.current = null;
        if (mountedRef.current) setExportPending(false);
      }
    }
  }

  return {
    run,
    progress,
    formalData,
    loading,
    loadError,
    pendingAction,
    mutationError,
    mutationOutcomeUnknown,
    exportPending,
    exportError,
    socketError,
    load,
    performAction,
    downloadExport,
    clearMutationError: () => setMutationError(""),
    clearExportError: () => setExportError(""),
    resetSocketError,
  };
}

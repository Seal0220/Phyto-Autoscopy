"use client";

import {
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";

import { downloadAnalysisExport } from "@/features/AnalysisRun/lib/analysisRunApiUtils";
import { normalizeAnalysisRun } from "@/features/AnalysisRun/lib/analysisRunUtils";
import {
  abortRequest,
  messageFromError,
} from "@/lib/httpUtils";

import { normalizeReprojectionErrors } from "@/features/ReprojectionErrors/lib/reprojectionUtils";
import { loadTrajectoryResults } from "../lib/trajectoryApiUtils";
import {
  normalizeDetectionSummary,
  normalizeTrajectory,
  normalizeTrajectoryFrameOverlay,
} from "../lib/trajectoryUtils";

export default function useTrajectoryResults({
  analysisId,
}) {
  const [run, setRun] = useState(null);
  const [trajectory, setTrajectory] = useState([]);
  const [errors, setErrors] = useState([]);
  const [summary, setSummary] = useState(null);
  const [calibration, setCalibration] = useState(null);
  const [frameOverlay, setFrameOverlay] = useState(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [exportPending, setExportPending] = useState(false);
  const [exportError, setExportError] = useState("");
  const mountedRef = useRef(false);
  const loadControllerRef = useRef(null);
  const exportControllerRef = useRef(null);
  const generationRef = useRef(0);

  const load = useCallback(async () => {
    const generation = generationRef.current + 1;
    generationRef.current = generation;
    abortRequest(
      loadControllerRef.current,
      "已由新的分析結果讀取取代。",
    );
    const controller = new AbortController();
    loadControllerRef.current = controller;
    setLoading(true);
    setLoadError("");

    try {
      const payload = await loadTrajectoryResults(
        analysisId,
        controller.signal,
      );
      if (!mountedRef.current || generation !== generationRef.current) return;
      setRun(normalizeAnalysisRun(payload.run));
      setTrajectory(normalizeTrajectory(payload.trajectory));
      setErrors(normalizeReprojectionErrors(payload.errors));
      setSummary(normalizeDetectionSummary(payload.summary));
      setCalibration(payload.calibration && typeof payload.calibration === "object"
        ? payload.calibration
        : null
      );
      setFrameOverlay(payload.frame && typeof payload.frame === "object"
        ? normalizeTrajectoryFrameOverlay(payload.frame)
        : null
      );
      setLoadError("");
    } catch (error) {
      if (error?.name === "AbortError") return;
      if (mountedRef.current && generation === generationRef.current) {
        setLoadError(messageFromError(
          error,
          "讀取分析結果失敗。",
        ));
      }
    } finally {
      if (loadControllerRef.current === controller) {
        loadControllerRef.current = null;
      }
      if (mountedRef.current && generation === generationRef.current) {
        setLoading(false);
      }
    }
  }, [analysisId]);

  useEffect(() => {
    mountedRef.current = true;
    void load();

    return () => {
      mountedRef.current = false;
      generationRef.current += 1;
      abortRequest(loadControllerRef.current);
      abortRequest(exportControllerRef.current);
    };
  }, [load]);

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
    trajectory,
    errors,
    summary,
    calibration,
    frameOverlay,
    loading,
    loadError,
    exportPending,
    exportError,
    load,
    downloadExport,
    clearExportError: () => setExportError(""),
  };
}

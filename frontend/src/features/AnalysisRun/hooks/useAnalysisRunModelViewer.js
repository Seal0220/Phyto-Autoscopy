"use client";

import { useEffect, useRef, useState } from "react";
import { analysisArtifactUrl } from "@/lib/analysisImageUtils";
import { landmarkInModelSpace } from "../lib/analysisModelCoordinateUtils";

const EMPTY_POINT_IDS = [];

export default function useAnalysisRunModelViewer({
  analysisId,
  reference,
  landmark,
  selectedPointId,
  pointIds = EMPTY_POINT_IDS,
  disabled,
  onPointChange,
  onPointMove,
  onPointRemove,
  tipPicking = false,
}) {
  const element = useRef(null);
  const viewer = useRef(null);
  const current = useRef({ reference, landmark, selectedPointId, pointIds, disabled, onPointChange, onPointMove, onPointRemove });
  const [ready, setReady] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [progress, setProgress] = useState(0);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    current.current = { reference, landmark, selectedPointId, pointIds, disabled, onPointChange, onPointMove, onPointRemove };
    viewer.current?.setDisabled(disabled);
    viewer.current?.setSelection(selectedPointId, pointIds);
    viewer.current?.setTip(landmarkInModelSpace(landmark, reference));
  }, [reference, landmark, selectedPointId, pointIds, disabled, onPointChange, onPointMove, onPointRemove]);

  useEffect(() => {
    let active = true;
    let instance;
    let timeout;
    setReady(false);
    setError("");
    setNotice("");
    setProgress(0);
    async function load() {
      try {
        if (!current.current.reference.gaussian_path) throw new Error("Missing Gaussian model");
        const { createModelViewer } = await import("../lib/analysisModelViewer");
        if (!active) return;
        instance = createModelViewer({
          element: element.current,
          reference: current.current.reference,
          tipPicking,
          onPick: current.current.onPointChange ? (pointId) => {
            if (active && !current.current.disabled) current.current.onPointChange?.(pointId);
          } : undefined,
          onMove: (pointId, nextPointId) => active && !current.current.disabled
            && current.current.onPointMove?.(pointId, nextPointId),
          onRemove: (pointId) => {
            if (active && !current.current.disabled) current.current.onPointRemove?.(pointId);
          },
          onNotice: (message) => { if (active) setNotice(message); },
          onProgress: (percent) => { if (active) setProgress(percent); },
        });
        viewer.current = instance;
        instance.setDisabled(current.current.disabled);
        timeout = setTimeout(() => {
          if (!active) return;
          setError("模型載入逾時，請重試。");
          setReady(false);
          if (viewer.current === instance) viewer.current = null;
          void instance.dispose().catch(() => {});
        }, 120_000);
        await instance.load(analysisArtifactUrl(analysisId, current.current.reference.gaussian_path));
        clearTimeout(timeout);
        if (!active || viewer.current !== instance) return;
        instance.setSelection(current.current.selectedPointId, current.current.pointIds);
        instance.setTip(landmarkInModelSpace(current.current.landmark, current.current.reference));
        setReady(true);
      } catch {
        clearTimeout(timeout);
        if (active) {
          setError("無法載入3D模型，請重試或確認 WebGL 可用。");
          if (viewer.current === instance) viewer.current = null;
          if (instance) void instance.dispose().catch(() => {});
        }
      }
    }
    void load();
    return () => {
      active = false;
      clearTimeout(timeout);
      if (viewer.current === instance) viewer.current = null;
      if (instance) void instance.dispose().catch(() => {});
    };
  }, [analysisId, reference.signature, attempt, tipPicking]);

  return {
    element, ready, error, notice, progress,
    reset: () => { viewer.current?.reset(); setNotice(""); },
    retry: () => setAttempt((previous) => previous + 1),
  };
}

"use client";

import { useEffect, useState } from "react";
import { requestAnalysisResource } from "../lib/analysisRunApiUtils";

export default function useAnalysisRunFeatureCorrespondences({
  analysisId,
  roundKey,
  snapshotId,
  enabled,
  modelStatus,
}) {
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    setResult(null);
    setError("");
    setLoading(false);
    if (!enabled || !snapshotId || modelStatus !== "completed") return;
    const controller = new AbortController();
    setLoading(true);
    let active = true;
    const query = new URLSearchParams({ round_key: roundKey, snapshot_id: snapshotId });
    void requestAnalysisResource(`/api/analysis/${encodeURIComponent(analysisId)}/round-feature-correspondences?${query}`, {
      signal: controller.signal,
    }).then((payload) => {
      if (active) setResult(payload);
    }).catch((failure) => {
      if (active && failure?.name !== "AbortError") setError("讀取葉片特徵配對失敗，請重試。");
    }).finally(() => {
      if (active) setLoading(false);
    });
    return () => {
      active = false;
      controller.abort();
    };
  }, [analysisId, roundKey, snapshotId, enabled, modelStatus, retry]);
  return { result, error, loading, retry: () => setRetry((value) => value + 1) };
}

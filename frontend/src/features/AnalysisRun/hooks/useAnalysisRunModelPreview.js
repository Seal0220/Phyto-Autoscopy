"use client";

import {
  useCallback,
  useEffect,
  useState,
} from "react";

import { requestAnalysisResource } from "../lib/analysisRunApiUtils";

export default function useAnalysisRunModelPreview({
  analysisId,
  model,
}) {
  const [reference, setReference] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const retry = useCallback(() => setAttempt((value) => value + 1), []);
  const roundKey = model.round_key;

  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    setReference(null);
    setLoading(true);
    setError("");
    const query = new URLSearchParams({ round_key: roundKey });
    void requestAnalysisResource(
      `/api/analysis/${encodeURIComponent(analysisId)}/round-model-preview?${query}`,
      { signal: controller.signal },
    ).then((payload) => {
      if (active) setReference(payload);
    }).catch((failure) => {
      if (active && failure?.name !== "AbortError") {
        setError("讀取此輪模型失敗，請重試。");
      }
    }).finally(() => {
      if (active) setLoading(false);
    });
    return () => {
      active = false;
      controller.abort();
    };
  }, [analysisId, roundKey, model.model_path, model.plant_model_path, model.model_id, model.training_iterations, model.training_duration_seconds, attempt]);

  return { reference, loading, error, retry };
}

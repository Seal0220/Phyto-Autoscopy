"use client";

import { useEffect, useRef, useState } from "react";
import { messageFromError } from "@/lib/httpUtils";
import { requestAnalysisResource, UnknownAnalysisMutationOutcomeError } from "../lib/analysisRunApiUtils";

export default function useAnalysisRunRoundRetry({ analysisId, roundKey, onAccepted }) {
  const mounted = useRef(false);
  const controller = useRef(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [unknown, setUnknown] = useState(false);
  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; controller.current?.abort(); };
  }, []);
  async function retry() {
    if (controller.current || unknown) return;
    const request = new AbortController();
    controller.current = request;
    setSaving(true);
    setError("");
    try {
      const result = await requestAnalysisResource(
        `/api/analysis/${encodeURIComponent(analysisId)}/round-retry?round_key=${encodeURIComponent(roundKey)}`,
        { method: "POST", signal: request.signal, timeoutMs: 120_000 },
      );
      if (mounted.current) onAccepted(result);
    } catch (failure) {
      if (mounted.current && failure.name !== "AbortError") {
        setUnknown(failure instanceof UnknownAnalysisMutationOutcomeError);
        setError(messageFromError(failure, "本輪重試失敗，請重新讀取狀態。"));
      }
    } finally {
      if (controller.current === request) {
        controller.current = null;
        if (mounted.current) setSaving(false);
      }
    }
  }
  return { saving, error, unknown, retry };
}

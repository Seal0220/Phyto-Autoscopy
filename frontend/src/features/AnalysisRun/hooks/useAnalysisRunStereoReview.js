"use client";

import {
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";
import { messageFromError } from "@/lib/httpUtils";
import {
  requestAnalysisResource,
  UnknownAnalysisMutationOutcomeError,
} from "../lib/analysisRunApiUtils";
import { stereoReviewRequest } from "../lib/analysisStereoReviewUtils";

export default function useAnalysisRunStereoReview({
  analysisId,
  open,
  onAccepted,
}) {
  const [review, setReview] = useState(null);
  const [pairs, setPairs] = useState([{ top: null, side: null }]);
  const [selected, setSelected] = useState(0);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [unknown, setUnknown] = useState(false);
  const mounted = useRef(false);
  const controller = useRef(null);
  const mutation = useRef(null);
  const path = `/api/analysis/${encodeURIComponent(analysisId)}/stereo-review`;

  const load = useCallback(async () => {
    controller.current?.abort();
    const request = new AbortController();
    controller.current = request;
    setLoading(true);
    setError("");
    try {
      const payload = await requestAnalysisResource(
        path,
        { signal: request.signal },
      );
      if (!mounted.current || controller.current !== request) return;
      setReview(payload);
      const draft = payload.draft?.correspondences;
      if (Array.isArray(draft) && draft.length) {
        setPairs(draft);
        setSelected(0);
      }
      setUnknown(false);
    } catch (failure) {
      if (failure.name !== "AbortError" && mounted.current && controller.current === request) {
        setError(messageFromError(failure, "讀取雙鏡頭人工配對影像失敗。"));
      }
    } finally {
      if (controller.current === request) {
        controller.current = null;
        if (mounted.current) setLoading(false);
      }
    }
  }, [path]);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      controller.current?.abort();
      mutation.current?.abort();
    };
  }, [analysisId]);

  useEffect(() => {
    if (open && !review) void load();
  }, [open, review, load]);

  function changePoint(
    camera,
    point,
  ) {
    if (saving || unknown) return;
    setPairs((previous) => previous.map(
      (pair, index) => index === selected ? { ...pair, [camera]: point } : pair,
    ));
  }

  function addPair() {
    if (pairs.length >= 200) return;
    setPairs((previous) => [...previous, { top: null, side: null }]);
    setSelected(pairs.length);
  }

  function removePair() {
    setPairs((previous) => previous.length > 1
      ? previous.filter((_, index) => index !== selected)
      : [{ top: null, side: null }]);
    setSelected(Math.max(0, selected - 1));
  }

  async function submit() {
    if (saving || unknown || mutation.current || !review) return;
    const request = new AbortController();
    mutation.current = request;
    setSaving(true);
    setError("");
    try {
      const result = await requestAnalysisResource(
        path,
        {
          method: "POST",
          body: stereoReviewRequest(
            review.views,
            pairs,
          ),
          signal: request.signal,
          timeoutMs: 120_000,
        },
      );
      if (mounted.current) onAccepted(result);
    } catch (failure) {
      if (failure.name !== "AbortError" && mounted.current) {
        setUnknown(failure instanceof UnknownAnalysisMutationOutcomeError);
        setError(messageFromError(failure, "人工配對未通過驗證，請修正位置後再試。"));
      }
    } finally {
      if (mutation.current === request) {
        mutation.current = null;
        if (mounted.current) setSaving(false);
      }
    }
  }

  return {
    review,
    pairs,
    selected,
    setSelected,
    loading,
    saving,
    error,
    unknown,
    load,
    changePoint,
    addPair,
    removePair,
    submit,
  };
}

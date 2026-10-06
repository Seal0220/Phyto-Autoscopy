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
import {
  stereoPairsAfterRefresh,
  stereoPairsWithModelPoint,
  stereoPairsWithMovedModelPoint,
  stereoPairsWithoutPair,
  stereoReviewRequest,
} from "../lib/analysisStereoReviewUtils";
import { knownModelPoint } from "../lib/analysisModelReferenceUtils";

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
  const [validation, setValidation] = useState(null);
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
      setValidation(payload.validation ?? null);
      const draft = payload.draft?.correspondences;
      if (Array.isArray(draft) && draft.length) {
        setPairs(draft);
        setSelected(0);
      } else {
        setPairs([{ top: null, side: null }]);
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
    pairIndex = selected,
  ) {
    if (saving || unknown || !Number.isInteger(pairIndex) || pairIndex < 0 || pairIndex >= pairs.length) return;
    setValidation(null);
    setError("");
    setPairs((previous) => previous.map(
      (pair, index) => index === pairIndex ? { ...pair, [camera]: point } : pair,
    ));
    setSelected(pairIndex);
  }

  function addPair() {
    if (saving || unknown || pairs.length >= 200) return;
    setValidation(null);
    setError("");
    setPairs((previous) => [...previous, { top: null, side: null }]);
    setSelected(pairs.length);
  }

  function changeModelPoint(pointId) {
    if (saving || unknown || !review?.reference) return;
    const id = Number(pointId);
    if (!knownModelPoint(review.reference, id)) return;
    const next = stereoPairsWithModelPoint(pairs, selected, id);
    if (!next) { setError("參照點已達 200 組，請先刪除不需要的配對。"); return; }
    setValidation(null);
    setError("");
    setPairs(next.pairs);
    setSelected(next.selected);
  }

  function moveModelPoint(
    pointId,
    nextPointId,
  ) {
    if (saving || unknown || !review?.reference || !knownModelPoint(review.reference, nextPointId)) return false;
    const next = stereoPairsWithMovedModelPoint(pairs, pointId, nextPointId);
    if (!next) {
      setError("此位置已有參照點，請選擇其他位置。");
      return false;
    }
    setValidation(null);
    setError("");
    setPairs(next.pairs);
    setSelected(next.selected);
    return true;
  }

  function removePair(index = selected) {
    if (saving || unknown) return;
    const next = stereoPairsWithoutPair(pairs, selected, index);
    setValidation(null);
    setError("");
    setPairs(next.pairs);
    setSelected(next.selected);
  }

  function removeModelPoint(pointId) {
    const index = pairs.findIndex((pair) => pair.model_point_id === pointId);
    if (index >= 0) removePair(index);
  }

  async function submit() {
    if (saving || unknown || mutation.current || !review) return;
    const body = stereoReviewRequest(
      review.views,
      pairs,
      review.reference,
    );
    // Align displayed pair numbers with the submitted, complete correspondences.
    setSelected(Math.max(0, body.correspondences.indexOf(pairs[selected])));
    setPairs(body.correspondences);
    const request = new AbortController();
    mutation.current = request;
    setSaving(true);
    setError("");
    setValidation(null);
    try {
      const result = await requestAnalysisResource(
        path,
        {
          method: "POST",
          body,
          signal: request.signal,
          timeoutMs: 120_000,
        },
      );
      if (mounted.current) onAccepted(result);
    } catch (failure) {
      if (failure.name !== "AbortError" && mounted.current) {
        setUnknown(failure instanceof UnknownAnalysisMutationOutcomeError);
        setError(messageFromError(failure, "人工配對未通過驗證，請修正位置後再試。"));
        if (!(failure instanceof UnknownAnalysisMutationOutcomeError)) {
          try {
            const payload = await requestAnalysisResource(
              path,
              { signal: request.signal },
            );
            if (mounted.current && mutation.current === request) {
              const updatedPairs = stereoPairsAfterRefresh(body.correspondences, review, payload);
              setPairs(updatedPairs);
              setSelected((previous) => Math.min(previous, Math.max(0, updatedPairs.length - 1)));
              setReview(payload);
              setValidation(payload.validation ?? null);
            }
          } catch {
            // Preserve the validation error when its read-only details cannot be fetched.
          }
        }
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
    validation,
    load,
    changePoint,
    changeModelPoint,
    moveModelPoint,
    removeModelPoint,
    addPair,
    removePair,
    submit,
  };
}

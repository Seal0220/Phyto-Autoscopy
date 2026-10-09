"use client";

import { useEffect, useRef, useState } from "react";
import { messageFromError } from "@/lib/httpUtils";
import { saveFormalTipCorrection } from "@/features/TipReview/lib/formalTipReviewApiUtils";
import { UnknownAnalysisMutationOutcomeError } from "../lib/analysisRunApiUtils";
import { tipCorrectionPayload } from "../lib/analysisRoundTipUtils";

export default function useAnalysisRunTipCorrection({
  analysisId,
  roundKey,
  views,
  correction,
  landmark,
  onSaved,
}) {
  const [points, setPoints] = useState({});
  const [modelSelection, setModelSelection] = useState(null);
  const [saving, setSaving] = useState(false);
  const [unknown, setUnknown] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const controller = useRef(null);
  const mounted = useRef(false);
  const savedCorrection = useRef({ correction, landmark });
  savedCorrection.current = { correction, landmark };

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      controller.current?.abort();
      controller.current = null;
    };
  }, [analysisId, roundKey]);

  useEffect(() => {
    const saved = savedCorrection.current.correction;
    const observations = saved?.observations?.length ? saved.observations
      : saved ? (saved.projected_observations || []).filter((item) => saved.supporting_views?.includes(item.view_id))
        : savedCorrection.current.landmark?.image_observations || [];
    setPoints(Object.fromEntries((observations || []).map((item) => [item.view_id, { x_px: item.x_px, y_px: item.y_px }])));
    setModelSelection(saved?.model_point_id != null ? {
      pointId: saved.model_point_id, signature: saved.model_signature,
    } : null);
    setError("");
    setNotice("");
    setUnknown(false);
    setSaving(false);
  }, [analysisId, roundKey, correction?.correction_id, landmark?.tip_id]);

  const updatePoint = (
    viewId,
    point,
  ) => {
    if (controller.current || unknown) return;
    setPoints((previous) => ({ ...previous, [viewId]: point }));
    setModelSelection(null);
    setError("");
    setNotice("");
  };
  const removePoint = (viewId) => {
    if (controller.current || unknown) return;
    setPoints((previous) => {
      const next = { ...previous };
      delete next[viewId];
      return next;
    });
    setNotice("");
  };
  const selectModelPoint = (
    pointId,
    reference,
  ) => {
    if (controller.current || unknown) return;
    setModelSelection(pointId == null ? null : { pointId, signature: reference.signature });
    setPoints({});
    setError("");
    setNotice("");
  };
  async function save() {
    if (controller.current || unknown) return;
    let payload;
    try {
      payload = tipCorrectionPayload(roundKey, views, points, modelSelection);
    } catch (failure) {
      setError(failure.message);
      return;
    }
    const request = new AbortController();
    controller.current = request;
    setSaving(true);
    setError("");
    setNotice("");
    try {
      const result = await saveFormalTipCorrection(analysisId, payload, request.signal);
      if (!mounted.current || controller.current !== request) return;
      setNotice(result.tracking_seed_confirmed
        ? "尖端影像已確認，後續輪次將延續此目標追蹤。三維位置會在量測校正通過後更新。"
        : result.pending_alignment ? "尖端標記已儲存，待相機姿態可用後計算三維位置。" : "尖端已更新，軌跡圖表已同步。");
      try {
        if (await onSaved?.() === false && mounted.current) {
          setError("尖端已儲存，但畫面更新失敗，請重新讀取。");
        }
      } catch {
        if (mounted.current) setError("尖端已儲存，但畫面更新失敗，請重新讀取。");
      }
    } catch (failure) {
      if (mounted.current && !request.signal.aborted) {
        setUnknown(failure instanceof UnknownAnalysisMutationOutcomeError);
        setError(messageFromError(failure, "儲存尖端失敗，請重新讀取確認結果。"));
      }
    } finally {
      if (controller.current === request) {
        controller.current = null;
        if (mounted.current) setSaving(false);
      }
    }
  }
  async function refresh() {
    if (controller.current) return;
    try {
      if (await onSaved?.() !== false && mounted.current) {
        setUnknown(false);
        setError("");
      }
    } catch {
      if (mounted.current) setError("重新讀取尖端結果失敗，請重試。");
    }
  }
  return { points, modelSelection, saving, unknown, error, notice, updatePoint, removePoint, selectModelPoint, save, refresh };
}

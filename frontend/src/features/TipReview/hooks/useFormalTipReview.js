"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import {
  abortRequest,
  messageFromError,
} from "@/lib/httpUtils";

import {
  completeFormalTipReview,
  deleteFormalTipCorrection,
  loadFormalTipReview,
  saveFormalTipCorrection,
} from "../lib/formalTipReviewApiUtils";

const EMPTY_DATA = {
  run: null,
  rounds: [],
  views: [],
  models: [],
  landmarks: [],
  observations: [],
  corrections: [],
  trajectory: [],
};

function initialDraft(
  landmark,
  correction,
) {
  const resolved = correction?.corrected_tip || landmark;
  const supportingViews = new Set(correction?.supporting_views || []);
  const correctionMode = correction?.correction_type
    || (correction?.invalid ? "invalid" : "views");

  return {
    mode: correctionMode,
    reason: "",
    invalid: Boolean(correction?.invalid),
    observations: Object.fromEntries(
      (correction?.projected_observations || [])
        .filter((item) => (
          correctionMode === "point"
          || supportingViews.has(item.view_id)
        ))
        .map((item) => [item.view_id, {
          x_px: Number(item.x_px),
          y_px: Number(item.y_px),
        }]),
    ),
    point: {
      x: resolved?.x_mm ?? "",
      y: resolved?.y_mm ?? "",
      z: resolved?.z_mm ?? "",
    },
  };
}

export default function useFormalTipReview({
  analysisId,
}) {
  const [data, setData] = useState(EMPTY_DATA);
  const [selectedRoundKey, setSelectedRoundKey] = useState("");
  const [draft, setDraft] = useState(() => initialDraft(null, null));
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [pendingAction, setPendingAction] = useState("");
  const [mutationError, setMutationError] = useState("");
  const mountedRef = useRef(false);
  const loadControllerRef = useRef(null);
  const mutationControllerRef = useRef(null);

  const load = useCallback(async ({
    preserveSelection = true,
  } = {}) => {
    abortRequest(
      loadControllerRef.current,
      "已由新的尖端標記資料讀取取代。",
    );
    const controller = new AbortController();
    loadControllerRef.current = controller;
    setLoading(true);
    setLoadError("");

    try {
      const payload = await loadFormalTipReview(
        analysisId,
        controller.signal,
      );
      if (!mountedRef.current) return false;
      setData(payload);
      setSelectedRoundKey((previous) => {
        if (
          preserveSelection
          && previous
          && payload.rounds.some((item) => item.round_key === previous)
        ) {
          return previous;
        }
        const attention = payload.rounds.find((item) => (
          ["tip_invalid", "tip_only", "model_failed"].includes(item.status)
        ));
        return attention?.round_key || payload.rounds[0]?.round_key || "";
      });
      return true;
    } catch (error) {
      if (error?.name !== "AbortError" && mountedRef.current) {
        setLoadError(messageFromError(
          error,
          "讀取三維尖端標記資料失敗。",
        ));
      }
      return false;
    } finally {
      if (loadControllerRef.current === controller) {
        loadControllerRef.current = null;
      }
      if (mountedRef.current) setLoading(false);
    }
  }, [analysisId]);

  useEffect(() => {
    mountedRef.current = true;
    void load({ preserveSelection: false });

    return () => {
      mountedRef.current = false;
      abortRequest(loadControllerRef.current, "尖端標記頁面已關閉。");
      abortRequest(mutationControllerRef.current, "尖端標記頁面已關閉。");
    };
  }, [load]);

  const selectedRound = useMemo(() => data.rounds.find(
    (item) => item.round_key === selectedRoundKey,
  ) || null, [
    data.rounds,
    selectedRoundKey,
  ]);
  const selectedViews = useMemo(() => data.views.filter(
    (item) => item.round_key === selectedRoundKey,
  ), [
    data.views,
    selectedRoundKey,
  ]);
  const selectedModel = useMemo(() => data.models.find(
    (item) => item.round_key === selectedRoundKey,
  ) || null, [
    data.models,
    selectedRoundKey,
  ]);
  const automaticLandmark = useMemo(() => data.landmarks.find(
    (item) => item.round_key === selectedRoundKey,
  ) || null, [
    data.landmarks,
    selectedRoundKey,
  ]);
  const roundCorrections = useMemo(() => data.corrections.filter(
    (item) => item.round_key === selectedRoundKey,
  ), [
    data.corrections,
    selectedRoundKey,
  ]);
  const latestCorrection = roundCorrections.at(-1) || null;
  const resolvedLandmark = latestCorrection?.corrected_tip || automaticLandmark;
  const selectedObservations = useMemo(() => data.observations.filter(
    (item) => item.round_key === selectedRoundKey,
  ), [
    data.observations,
    selectedRoundKey,
  ]);

  useEffect(() => {
    setDraft(initialDraft(automaticLandmark, latestCorrection));
  }, [
    automaticLandmark,
    latestCorrection,
    selectedRoundKey,
  ]);

  const selectRound = useCallback((roundKey) => {
    setSelectedRoundKey(roundKey);
    setMutationError("");
  }, []);

  const updateDraft = useCallback((key, value) => {
    setDraft((previous) => ({
      ...previous,
      [key]: value,
    }));
  }, []);

  const updateObservation = useCallback((viewId, point) => {
    setDraft((previous) => ({
      ...previous,
      mode: "views",
      invalid: false,
      observations: {
        ...previous.observations,
        [viewId]: point,
      },
    }));
  }, []);

  const removeObservation = useCallback((viewId) => {
    setDraft((previous) => {
      const observations = {
        ...previous.observations,
      };
      delete observations[viewId];
      return {
        ...previous,
        observations,
      };
    });
  }, []);

  const saveCorrection = useCallback(async () => {
    if (!selectedRoundKey) return false;
    const reason = draft.reason.trim();
    if (!reason) {
      setMutationError("請填寫尖端標記修正原因。");
      return false;
    }
    let payload = {
      round_key: selectedRoundKey,
      reason,
      invalid: draft.mode === "invalid",
    };
    if (draft.mode === "views") {
      const observations = Object.entries(draft.observations)
        .map(([viewId, point]) => ({
          view_id: viewId,
          x_px: Number(point.x_px),
          y_px: Number(point.y_px),
        }))
        .filter((item) => Number.isFinite(item.x_px) && Number.isFinite(item.y_px));
      if (observations.length < 2) {
        setMutationError("請至少在兩個不同視角指定尖端位置。");
        return false;
      }
      payload = {
        ...payload,
        observations,
        invalid: false,
      };
    } else if (draft.mode === "point") {
      const point = [
        Number(draft.point.x),
        Number(draft.point.y),
        Number(draft.point.z),
      ];
      if (!point.every(Number.isFinite)) {
        setMutationError("三維尖端位置必須填入有效的 X、Y、Z 毫米座標。");
        return false;
      }
      payload = {
        ...payload,
        corrected_point_mm: point,
        invalid: false,
      };
    }

    abortRequest(
      mutationControllerRef.current,
      "已由新的尖端標記修正取代。",
    );
    const controller = new AbortController();
    mutationControllerRef.current = controller;
    setPendingAction("save");
    setMutationError("");
    try {
      await saveFormalTipCorrection(
        analysisId,
        payload,
        controller.signal,
      );
      if (!mountedRef.current) return false;
      await load();
      return true;
    } catch (error) {
      if (error?.name !== "AbortError" && mountedRef.current) {
        setMutationError(messageFromError(
          error,
          "儲存尖端標記修正失敗。",
        ));
      }
      return false;
    } finally {
      if (mutationControllerRef.current === controller) {
        mutationControllerRef.current = null;
      }
      if (mountedRef.current) setPendingAction("");
    }
  }, [
    analysisId,
    draft,
    load,
    selectedRoundKey,
  ]);

  const deleteCorrection = useCallback(async (correctionId) => {
    const controller = new AbortController();
    abortRequest(
      mutationControllerRef.current,
      "已由新的尖端標記操作取代。",
    );
    mutationControllerRef.current = controller;
    setPendingAction(`delete-${correctionId}`);
    setMutationError("");
    try {
      await deleteFormalTipCorrection(
        analysisId,
        correctionId,
        controller.signal,
      );
      if (!mountedRef.current) return false;
      await load();
      return true;
    } catch (error) {
      if (error?.name !== "AbortError" && mountedRef.current) {
        setMutationError(messageFromError(
          error,
          "刪除尖端標記修正失敗。",
        ));
      }
      return false;
    } finally {
      if (mutationControllerRef.current === controller) {
        mutationControllerRef.current = null;
      }
      if (mountedRef.current) setPendingAction("");
    }
  }, [
    analysisId,
    load,
  ]);

  const completeReview = useCallback(async () => {
    const controller = new AbortController();
    abortRequest(
      mutationControllerRef.current,
      "已由完成尖端標記確認取代。",
    );
    mutationControllerRef.current = controller;
    setPendingAction("complete");
    setMutationError("");
    try {
      const run = await completeFormalTipReview(
        analysisId,
        controller.signal,
      );
      if (!mountedRef.current) return null;
      setData((previous) => ({
        ...previous,
        run,
      }));
      return run;
    } catch (error) {
      if (error?.name !== "AbortError" && mountedRef.current) {
        setMutationError(messageFromError(
          error,
          "完成尖端標記確認失敗。",
        ));
      }
      return null;
    } finally {
      if (mutationControllerRef.current === controller) {
        mutationControllerRef.current = null;
      }
      if (mountedRef.current) setPendingAction("");
    }
  }, [analysisId]);

  return {
    ...data,
    selectedRoundKey,
    selectedRound,
    selectedViews,
    selectedModel,
    automaticLandmark,
    resolvedLandmark,
    selectedObservations,
    roundCorrections,
    latestCorrection,
    draft,
    loading,
    loadError,
    pendingAction,
    mutationError,
    load,
    selectRound,
    updateDraft,
    updateObservation,
    removeObservation,
    saveCorrection,
    deleteCorrection,
    completeReview,
    clearMutationError: () => setMutationError(""),
  };
}

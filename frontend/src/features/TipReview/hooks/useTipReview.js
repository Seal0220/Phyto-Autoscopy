"use client";

import {
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";

import {
  performAnalysisRunAction,
  UnknownAnalysisMutationOutcomeError,
} from "@/features/AnalysisRun/lib/analysisRunApiUtils";
import {
  normalizeAnalysisRun,
  normalizeFramePairs,
} from "@/features/AnalysisRun/lib/analysisRunUtils";
import {
  abortRequest,
  messageFromError,
} from "@/lib/httpUtils";

import {
  deleteTipCorrection,
  loadTipReviewCorrections,
  loadTipReviewFrame,
  loadTipReviewIndex,
  saveTipCorrection,
} from "../lib/tipReviewApiUtils";
import {
  correctionPayload,
  initialCorrectionDraft,
  latestCorrection,
  normalizeCorrection,
  normalizeFrameDetail,
  normalizedFrameIds,
} from "../lib/tipReviewUtils";

const PLAYBACK_INTERVAL_MS = 800;

export default function useTipReview({
  analysisId,
}) {
  const [run, setRun] = useState(null);
  const [frameIds, setFrameIds] = useState([]);
  const [indexedFrameCount, setIndexedFrameCount] = useState(0);
  const [currentFrameId, setCurrentFrameId] = useState(null);
  const [frame, setFrame] = useState(null);
  const [corrections, setCorrections] = useState([]);
  const [drafts, setDrafts] = useState({
    top: null,
    side: null,
  });
  const [activeCamera, setActiveCamera] = useState("top");
  const [playing, setPlaying] = useState(false);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [frameLoading, setFrameLoading] = useState(false);
  const [frameError, setFrameError] = useState("");
  const [pendingAction, setPendingAction] = useState("");
  const [mutationError, setMutationError] = useState("");
  const [mutationOutcomeUnknown, setMutationOutcomeUnknown] = useState(false);
  const mountedRef = useRef(false);
  const indexControllerRef = useRef(null);
  const frameControllerRef = useRef(null);
  const mutationControllerRef = useRef(null);
  const correctionsRef = useRef([]);
  const indexGenerationRef = useRef(0);
  const frameGenerationRef = useRef(0);

  const applyFrame = useCallback((payload) => {
    const normalized = normalizeFrameDetail(payload);
    const frameCorrections = correctionsRef.current.filter(
      (correction) => correction.frame_id === normalized.pair.frame_id,
    );
    const combinedCorrections = frameCorrections.length > 0
      ? frameCorrections
      : normalized.corrections;

    setFrame({
      ...normalized,
      corrections: combinedCorrections,
    });
    setDrafts({
      top: initialCorrectionDraft(
        normalized.topDetection,
        combinedCorrections,
        "top",
      ),
      side: initialCorrectionDraft(
        normalized.sideDetection,
        combinedCorrections,
        "side",
      ),
    });
  }, []);

  const loadIndex = useCallback(async ({
    confirmMutation = false,
  } = {}) => {
    const generation = indexGenerationRef.current + 1;
    indexGenerationRef.current = generation;
    abortRequest(
      indexControllerRef.current,
      "已由新的修正索引讀取取代。",
    );
    const controller = new AbortController();
    indexControllerRef.current = controller;
    setLoading(true);
    setLoadError("");

    try {
      const [runPayload, pairsPayload, framesPayload, correctionsPayload] = await loadTipReviewIndex(
        analysisId,
        controller.signal,
      );
      if (!mountedRef.current || generation !== indexGenerationRef.current) return false;

      const ids = normalizedFrameIds(normalizeFramePairs(pairsPayload));
      const normalizedCorrections = Array.isArray(correctionsPayload)
        ? correctionsPayload.map(normalizeCorrection).filter(Boolean)
        : [];
      correctionsRef.current = normalizedCorrections;
      setRun(normalizeAnalysisRun(runPayload));
      setFrameIds(ids);
      setIndexedFrameCount(Array.isArray(framesPayload) ? framesPayload.length : ids.length);
      setCorrections(normalizedCorrections);
      setCurrentFrameId((previous) => (
        previous != null && ids.includes(previous)
          ? previous
          : ids[0] ?? null
      ));
      setLoadError("");
      if (confirmMutation) {
        setMutationOutcomeUnknown(false);
        setMutationError("");
      }
      return true;
    } catch (error) {
      if (error?.name === "AbortError") return false;
      if (mountedRef.current && generation === indexGenerationRef.current) {
        setLoadError(messageFromError(
          error,
          "讀取人工修正資料失敗。",
        ));
      }
      return false;
    } finally {
      if (indexControllerRef.current === controller) {
        indexControllerRef.current = null;
      }
      if (mountedRef.current && generation === indexGenerationRef.current) {
        setLoading(false);
      }
    }
  }, [analysisId]);

  const loadFrame = useCallback(async (
    frameId = currentFrameId,
    {
      silent = false,
      signal,
    } = {},
  ) => {
    if (frameId == null) return false;
    const generation = frameGenerationRef.current + 1;
    frameGenerationRef.current = generation;
    abortRequest(
      frameControllerRef.current,
      "已由新的影格讀取取代。",
    );
    const controller = new AbortController();
    const abortFromCaller = () => abortRequest(
      controller,
      signal?.reason,
    );
    if (signal?.aborted) abortFromCaller();
    else signal?.addEventListener("abort", abortFromCaller, { once: true });
    frameControllerRef.current = controller;
    if (!silent) setFrameLoading(true);
    setFrameError("");

    try {
      const payload = await loadTipReviewFrame(
        analysisId,
        frameId,
        controller.signal,
      );
      if (!mountedRef.current || generation !== frameGenerationRef.current) return false;
      applyFrame(payload);
      setFrameError("");
      return true;
    } catch (error) {
      if (error?.name === "AbortError") return false;
      if (mountedRef.current && generation === frameGenerationRef.current) {
        setFrameError(messageFromError(
          error,
          `讀取影格 ${frameId} 失敗。`,
        ));
      }
      return false;
    } finally {
      signal?.removeEventListener("abort", abortFromCaller);
      if (frameControllerRef.current === controller) {
        frameControllerRef.current = null;
      }
      if (mountedRef.current && generation === frameGenerationRef.current && !silent) {
        setFrameLoading(false);
      }
    }
  }, [analysisId, applyFrame, currentFrameId]);

  useEffect(() => {
    mountedRef.current = true;
    void loadIndex();

    return () => {
      mountedRef.current = false;
      indexGenerationRef.current += 1;
      frameGenerationRef.current += 1;
      abortRequest(indexControllerRef.current);
      abortRequest(frameControllerRef.current);
      abortRequest(mutationControllerRef.current);
    };
  }, [loadIndex]);

  useEffect(() => {
    if (currentFrameId != null) void loadFrame(currentFrameId);
  }, [currentFrameId, loadFrame]);

  useEffect(() => {
    if (!playing || frameIds.length === 0) return undefined;
    const interval = window.setInterval(() => {
      if (frameLoading) return;
      const index = frameIds.indexOf(currentFrameId);
      if (index < 0 || index >= frameIds.length - 1) {
        setPlaying(false);
        return;
      }
      setCurrentFrameId(frameIds[index + 1]);
    }, PLAYBACK_INTERVAL_MS);

    return () => window.clearInterval(interval);
  }, [currentFrameId, frameIds, frameLoading, playing]);

  function updateDraft(
    cameraId,
    patch,
  ) {
    setDrafts((current) => ({
      ...current,
      [cameraId]: {
        ...(current[cameraId] || {
          point: null,
          invalid: false,
          reason: "",
        }),
        ...patch,
        dirty: true,
      },
    }));
  }

  function goRelative(direction) {
    setPlaying(false);
    setCurrentFrameId((previous) => {
      const index = frameIds.indexOf(previous);
      const nextIndex = Math.min(
        frameIds.length - 1,
        Math.max(0, index + direction),
      );
      return frameIds[nextIndex] ?? previous;
    });
  }

  function goToFrame(frameId) {
    const parsed = Number(frameId);
    if (!frameIds.includes(parsed)) {
      setFrameError("指定影格不存在於本次分析中。");
      return false;
    }
    setPlaying(false);
    setCurrentFrameId(parsed);
    setFrameError("");
    return true;
  }

  async function refreshCorrectionsAndFrame(controller) {
    const correctionsPayload = await loadTipReviewCorrections(
      analysisId,
      controller.signal,
    );
    if (!mountedRef.current) return;
    const normalized = Array.isArray(correctionsPayload)
      ? correctionsPayload.map(normalizeCorrection).filter(Boolean)
      : [];
    correctionsRef.current = normalized;
    setCorrections(normalized);
    if (currentFrameId == null) return;
    const frameLoaded = await loadFrame(currentFrameId, {
      silent: true,
      signal: controller.signal,
    });
    if (!frameLoaded) {
      throw new Error("重新讀取目前影格失敗。");
    }
  }

  async function performMutation(
    action,
    task,
  ) {
    if (
      pendingAction
      || mutationControllerRef.current
      || mutationOutcomeUnknown
    ) {
      return false;
    }
    const controller = new AbortController();
    mutationControllerRef.current = controller;
    setPendingAction(action);
    setMutationError("");

    try {
      await task(controller);
      if (!mountedRef.current) return false;
      setMutationError("");
      setMutationOutcomeUnknown(false);
      return true;
    } catch (error) {
      if (error?.name === "AbortError") return false;
      if (mountedRef.current) {
        setMutationOutcomeUnknown(
          error instanceof UnknownAnalysisMutationOutcomeError,
        );
        setMutationError(messageFromError(
          error,
          "人工修正操作失敗，請重新讀取後再試。",
        ));
      }
      return false;
    } finally {
      if (mutationControllerRef.current === controller) {
        mutationControllerRef.current = null;
        if (mountedRef.current) setPendingAction("");
      }
    }
  }

  async function saveActiveCorrection({
    advance = false,
  } = {}) {
    if (
      !frame
      || frame.pair.frame_id !== currentFrameId
      || !drafts[activeCamera]
    ) {
      setMutationError("目前影格尚未完成載入，請稍後再試。");
      return false;
    }
    let payload;
    try {
      payload = correctionPayload(
        frame.pair.frame_id,
        activeCamera,
        drafts[activeCamera],
      );
    } catch (error) {
      setMutationError(messageFromError(error, "人工修正資料無效。"));
      return false;
    }

    const saved = await performMutation(`save-${activeCamera}`, async (controller) => {
      const correction = normalizeCorrection(await saveTipCorrection(
        analysisId,
        payload,
        controller.signal,
      ));
      if (correction && mountedRef.current) {
        setCorrections((current) => {
          const next = [...current, correction];
          correctionsRef.current = next;
          return next;
        });
      }
    });

    if (saved) {
      await loadFrame(currentFrameId, { silent: true });
      if (advance) goRelative(1);
    }
    return saved;
  }

  async function removeCorrection(correctionId) {
    const removed = await performMutation(`delete-${correctionId}`, async (controller) => {
      await deleteTipCorrection(
        analysisId,
        correctionId,
        controller.signal,
      );
      if (mountedRef.current) {
        setCorrections((current) => {
          const next = current.filter(
            (correction) => correction.correction_id !== correctionId,
          );
          correctionsRef.current = next;
          return next;
        });
      }
    });

    if (removed) await loadFrame(currentFrameId, { silent: true });
    return removed;
  }

  async function clearActiveCorrection() {
    const currentCorrections = corrections.filter(
      (correction) => correction.frame_id === currentFrameId,
    );
    const correction = latestCorrection(currentCorrections, activeCamera);
    if (!correction) {
      setMutationError("目前影格的所選視角沒有可清除的人工修正。");
      return false;
    }
    return removeCorrection(correction.correction_id);
  }

  async function reconstruct() {
    return performMutation("reconstruct", async (controller) => {
      const payload = await performAnalysisRunAction(
        analysisId,
        "reconstruct",
        controller.signal,
      );
      if (mountedRef.current) setRun(normalizeAnalysisRun(payload));
    });
  }

  async function confirmMutationOutcome() {
    if (pendingAction || mutationControllerRef.current) return false;
    const controller = new AbortController();
    mutationControllerRef.current = controller;
    setPendingAction("confirm");
    setLoadError("");

    try {
      const indexLoaded = await loadIndex();
      if (!indexLoaded) return false;
      await refreshCorrectionsAndFrame(controller);
      if (mountedRef.current) {
        setMutationOutcomeUnknown(false);
        setMutationError("");
      }
      return true;
    } catch (error) {
      if (error?.name === "AbortError") return false;
      if (mountedRef.current) {
        setMutationError(messageFromError(
          error,
          "重新讀取修正狀態失敗，操作仍保持鎖定。",
        ));
      }
      return false;
    } finally {
      if (mutationControllerRef.current === controller) {
        mutationControllerRef.current = null;
        if (mountedRef.current) setPendingAction("");
      }
    }
  }

  const frameCorrections = corrections.filter(
    (correction) => correction.frame_id === currentFrameId,
  );

  return {
    run,
    frameIds,
    indexedFrameCount,
    currentFrameId,
    frame,
    frameCorrections,
    drafts,
    activeCamera,
    playing,
    loading,
    loadError,
    frameLoading,
    frameError,
    pendingAction,
    mutationError,
    mutationOutcomeUnknown,
    loadIndex,
    loadFrame,
    goRelative,
    goToFrame,
    setActiveCamera,
    setPlaying,
    updateDraft,
    saveActiveCorrection,
    removeCorrection,
    clearActiveCorrection,
    reconstruct,
    confirmMutationOutcome,
    clearMutationError: () => setMutationError(""),
  };
}

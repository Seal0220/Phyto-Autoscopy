"use client";

import {
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";

import {
  abortRequest,
  messageFromError,
  RequestTimeoutError,
  UnknownMutationOutcomeError,
} from "@/lib/httpUtils";

import {
  deleteCalibration,
  loadCalibrationDetail,
  runCalibrationStep,
} from "../lib/calibrationApiUtils";

export default function useCalibrationDetail(calibrationId) {
  const [profile, setProfile] = useState(null);
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState("");
  const [actionPending, setActionPending] = useState("");
  const [actionError, setActionError] = useState("");
  const [actionRequiresRefresh, setActionRequiresRefresh] = useState(false);
  const mountedRef = useRef(false);
  const loadGenerationRef = useRef(0);
  const loadControllerRef = useRef(null);
  const actionControllerRef = useRef(null);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      abortRequest(loadControllerRef.current);
      abortRequest(actionControllerRef.current);
    };
  }, []);

  const load = useCallback(async () => {
    abortRequest(
      loadControllerRef.current,
      "已由新的校正資料讀取取代。",
    );
    const controller = new AbortController();
    const generation = loadGenerationRef.current + 1;
    loadGenerationRef.current = generation;
    loadControllerRef.current = controller;
    setLoading(true);

    try {
      const [nextProfile, nextReport] = await loadCalibrationDetail(
        calibrationId,
        controller.signal,
      );
      if (
        !mountedRef.current
        || controller.signal.aborted
        || generation !== loadGenerationRef.current
      ) {
        return false;
      }
      setProfile(nextProfile);
      setReport(nextReport);
      setLoadError("");
      setActionError("");
      setActionRequiresRefresh(false);
      return true;
    } catch (error) {
      if (error?.name === "AbortError") return false;
      if (
        mountedRef.current
        && generation === loadGenerationRef.current
      ) {
        setLoadError(messageFromError(
          error,
          error instanceof RequestTimeoutError
            ? "讀取校正報告逾時，請重新讀取。"
            : "讀取校正報告失敗。",
        ));
      }
      return false;
    } finally {
      if (loadControllerRef.current === controller) {
        loadControllerRef.current = null;
        if (mountedRef.current) setLoading(false);
      }
    }
  }, [calibrationId]);

  useEffect(() => {
    void load();
  }, [load]);

  const runStep = useCallback(async (step) => {
    if (actionControllerRef.current || actionRequiresRefresh) return false;
    const controller = new AbortController();
    actionControllerRef.current = controller;
    setActionPending(step);
    setActionError("");
    setActionRequiresRefresh(false);

    try {
      const nextProfile = await runCalibrationStep(
        calibrationId,
        step,
        controller.signal,
      );
      if (!mountedRef.current || controller.signal.aborted) return false;
      setProfile(nextProfile);
      const refreshed = await load();
      if (!refreshed && mountedRef.current) {
        setActionError("校正步驟已完成，但報告重新讀取失敗。請重新讀取。");
      }
      return true;
    } catch (error) {
      if (error?.name === "AbortError" && !mountedRef.current) return false;
      if (mountedRef.current) {
        const unknown = error instanceof UnknownMutationOutcomeError;
        setActionRequiresRefresh(unknown);
        setActionError(unknown
          ? `${error.message} 請先重新讀取，勿立即重送。`
          : messageFromError(
            error,
            "執行相機校正步驟失敗。",
          )
        );
      }
      return false;
    } finally {
      if (actionControllerRef.current === controller) {
        actionControllerRef.current = null;
        if (mountedRef.current) setActionPending("");
      }
    }
  }, [
    actionRequiresRefresh,
    calibrationId,
    load,
  ]);

  const remove = useCallback(async () => {
    if (actionControllerRef.current || actionRequiresRefresh) return false;
    const controller = new AbortController();
    actionControllerRef.current = controller;
    setActionPending("delete");
    setActionError("");
    setActionRequiresRefresh(false);

    try {
      await deleteCalibration(
        calibrationId,
        controller.signal,
      );
      return mountedRef.current && !controller.signal.aborted;
    } catch (error) {
      if (error?.name === "AbortError" && !mountedRef.current) return false;
      if (mountedRef.current) {
        const unknown = error instanceof UnknownMutationOutcomeError;
        setActionRequiresRefresh(unknown);
        setActionError(unknown
          ? `${error.message} 請返回清單重新讀取。`
          : messageFromError(
            error,
            "刪除校正檔案失敗；若已被分析引用，系統不允許刪除。",
          )
        );
      }
      return false;
    } finally {
      if (actionControllerRef.current === controller) {
        actionControllerRef.current = null;
        if (mountedRef.current) setActionPending("");
      }
    }
  }, [
    actionRequiresRefresh,
    calibrationId,
  ]);

  return {
    profile,
    report,
    loading,
    loadError,
    actionPending,
    actionError,
    actionRequiresRefresh,
    load,
    runStep,
    remove,
    clearActionError: () => setActionError(""),
  };
}

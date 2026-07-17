"use client";

import {
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";

import {
  messageFromError,
  RequestTimeoutError,
  UnknownMutationOutcomeError,
} from "@/lib/httpUtils";

import {
  analysisMutationErrorMessage,
  createAnalysisRun,
  loadAnalysisSetupOptions,
  previewAnalysisSources,
  startAnalysisRun,
  validateAnalysisRun,
} from "../lib/analysisApiUtils";
import {
  analysisDefaultEndFrame,
  analysisSourcesFromPayload,
  buildAnalysisCreatePayload,
  calibrationProfilesFromPayload,
  createInitialAnalysisSetup,
  normalizeCreatedAnalysisRun,
  validateAnalysisSetupStep,
} from "../lib/analysisUtils";

function mutationOutcomeUnknown(error) {
  return error instanceof UnknownMutationOutcomeError;
}

export default function useAnalysisSetup({
  initialRecordId = "",
  initialStep = 1,
}) {
  const [sources, setSources] = useState([]);
  const [calibrations, setCalibrations] = useState([]);
  const [setup, setSetup] = useState(() => (
    createInitialAnalysisSetup(initialRecordId)
  ));
  const [currentStep, setCurrentStep] = useState(initialStep);
  const [highestStep, setHighestStep] = useState(initialStep);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState("");
  const [stepError, setStepError] = useState("");
  const [sourceScanning, setSourceScanning] = useState(false);
  const [createdRun, setCreatedRun] = useState(null);
  const [mutationPending, setMutationPending] = useState("");
  const [mutationError, setMutationError] = useState("");
  const [mutationRequiresRefresh, setMutationRequiresRefresh] = useState(false);
  const mountedRef = useRef(false);
  const loadingRef = useRef(false);
  const mutationRef = useRef("");
  const loadControllerRef = useRef(null);
  const mutationControllerRef = useRef(null);
  const sourceScanControllerRef = useRef(null);

  useEffect(() => {
    mountedRef.current = true;

    return () => {
      mountedRef.current = false;
      loadingRef.current = false;
      mutationRef.current = "";
      loadControllerRef.current?.abort();
      mutationControllerRef.current?.abort();
      sourceScanControllerRef.current?.abort();
      loadControllerRef.current = null;
      mutationControllerRef.current = null;
      sourceScanControllerRef.current = null;
    };
  }, []);

  const loadOptions = useCallback(async () => {
    if (loadingRef.current) return false;

    const controller = new AbortController();
    loadControllerRef.current = controller;
    loadingRef.current = true;
    setLoading(true);

    try {
      const [sourcePayload, calibrationPayload] = await loadAnalysisSetupOptions(
        controller.signal,
      );
      const nextSources = analysisSourcesFromPayload(sourcePayload);
      const nextCalibrations = calibrationProfilesFromPayload(calibrationPayload);

      if (!mountedRef.current || controller.signal.aborted) return false;

      setSources(nextSources);
      setCalibrations(nextCalibrations);
      setSetup((previous) => {
        const selectedSource = nextSources.find(
          (source) => source.record_id === previous.recordId,
        );
        if (!selectedSource) return previous;

        return {
          ...previous,
          endFrame: previous.endFrame || analysisDefaultEndFrame(selectedSource),
          cameraSources: {
            top: {
              enabled: true,
              path: previous.cameraSources.top.path
                || selectedSource.camera_directories.top,
            },
            side: {
              enabled: true,
              path: previous.cameraSources.side.path
                || selectedSource.camera_directories.side,
            },
            rotating: {
              enabled: previous.method === "top_side_rotating",
              path: previous.cameraSources.rotating.path
                || selectedSource.camera_directories.rotating,
            },
          },
        };
      });
      setLoadError("");
      return true;
    } catch (error) {
      if (error?.name === "AbortError") return false;

      const fallback = error instanceof RequestTimeoutError
        ? "讀取分析選項逾時，請重新讀取。"
        : "讀取分析選項失敗。";

      if (mountedRef.current) {
        setLoadError(messageFromError(
          error,
          fallback,
        ));
      }
      return false;
    } finally {
      if (loadControllerRef.current === controller) {
        loadControllerRef.current = null;
        loadingRef.current = false;
        if (mountedRef.current) setLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    void loadOptions();
  }, [loadOptions]);

  function selectRecord(recordId) {
    const source = sources.find((item) => item.record_id === recordId);
    setSetup((previous) => ({
      ...previous,
      recordId,
      endFrame: analysisDefaultEndFrame(source),
      cameraSources: {
        top: {
          enabled: true,
          path: source?.camera_directories?.top || "",
        },
        side: {
          enabled: true,
          path: source?.camera_directories?.side || "",
        },
        rotating: {
          enabled: previous.method === "top_side_rotating",
          path: source?.camera_directories?.rotating || "",
        },
      },
      sourcePreview: null,
    }));
    setStepError("");
  }

  function updateSetup(key, value) {
    setSetup((previous) => ({
      ...previous,
      [key]: value,
      ...(key === "method"
        ? {
          cameraSources: {
            ...previous.cameraSources,
            rotating: {
              ...previous.cameraSources.rotating,
              enabled: value === "top_side_rotating",
            },
          },
          sourcePreview: null,
        }
        : {}),
    }));
    setStepError("");
  }

  function updateCameraSource(
    cameraId,
    patch,
  ) {
    setSetup((previous) => ({
      ...previous,
      cameraSources: {
        ...previous.cameraSources,
        [cameraId]: {
          ...previous.cameraSources[cameraId],
          ...patch,
        },
      },
      sourcePreview: null,
    }));
    setStepError("");
  }

  async function scanSources() {
    sourceScanControllerRef.current?.abort();
    const controller = new AbortController();
    sourceScanControllerRef.current = controller;
    setSourceScanning(true);
    setStepError("");
    try {
      const preview = await previewAnalysisSources(
        {
          record_id: setup.recordId || null,
          method: setup.method,
          camera_sources: setup.cameraSources,
        },
        controller.signal,
      );
      if (!mountedRef.current || controller.signal.aborted) return false;
      setSetup((previous) => ({
        ...previous,
        sourcePreview: preview,
        endFrame: preview?.total_frame_count > 0
          ? String(preview.total_frame_count)
          : previous.endFrame,
      }));
      if (!preview?.ready) {
        setStepError(preview?.errors?.[0] || "影像目錄尚未具備分析條件。");
      }
      return Boolean(preview?.ready);
    } catch (error) {
      if (error?.name === "AbortError") return false;
      if (mountedRef.current) {
        setStepError(messageFromError(error, "掃描影像目錄失敗。"));
      }
      return false;
    } finally {
      if (sourceScanControllerRef.current === controller) {
        sourceScanControllerRef.current = null;
        if (mountedRef.current) setSourceScanning(false);
      }
    }
  }

  function updateRoi(
    camera,
    key,
    value,
  ) {
    const roiKey = camera === "top" ? "topRoi" : "sideRoi";
    setSetup((previous) => ({
      ...previous,
      [roiKey]: {
        ...previous[roiKey],
        [key]: value,
      },
    }));
    setStepError("");
  }

  function updateParameter(key, value) {
    setSetup((previous) => ({
      ...previous,
      parameters: {
        ...previous.parameters,
        [key]: value,
      },
    }));
    setStepError("");
  }

  function upsertCalibration(profile) {
    const [normalized] = calibrationProfilesFromPayload([profile]);
    if (!normalized?.calibration_id) return;
    setCalibrations((current) => [
      normalized,
      ...current.filter(
        (item) => item.calibration_id !== normalized.calibration_id,
      ),
    ]);
  }

  function goToStep(step) {
    if (createdRun || step < 1 || step > highestStep) return;
    setCurrentStep(step);
    setStepError("");
  }

  function nextStep() {
    try {
      validateAnalysisSetupStep(
        setup,
        currentStep,
        sources,
        calibrations,
      );
      const next = Math.min(5, currentStep + 1);
      setCurrentStep(next);
      setHighestStep((previous) => Math.max(previous, next));
      setStepError("");
      return true;
    } catch (error) {
      setStepError(messageFromError(
        error,
        "請確認目前步驟的設定。",
      ));
      return false;
    }
  }

  function previousStep() {
    if (createdRun) return;
    setCurrentStep((previous) => Math.max(1, previous - 1));
    setStepError("");
  }

  async function runMutation(
    kind,
    action,
  ) {
    if (mutationRef.current || mutationRequiresRefresh) return null;

    const controller = new AbortController();
    mutationControllerRef.current = controller;
    mutationRef.current = kind;
    setMutationPending(kind);
    setMutationError("");

    try {
      const result = await action(controller.signal);
      if (!mountedRef.current || controller.signal.aborted) return null;

      setMutationRequiresRefresh(false);
      return result;
    } catch (error) {
      if (error?.name === "AbortError") return null;

      if (mountedRef.current) {
        setMutationError(analysisMutationErrorMessage(
          error,
          kind === "create"
            ? "建立分析"
            : kind === "validate"
              ? "驗證分析"
              : "開始分析",
        ));
        setMutationRequiresRefresh(mutationOutcomeUnknown(error));
      }
      return null;
    } finally {
      if (mutationControllerRef.current === controller) {
        mutationControllerRef.current = null;
        mutationRef.current = "";
        if (mountedRef.current) setMutationPending("");
      }
    }
  }

  async function createRun() {
    try {
      validateAnalysisSetupStep(
        setup,
        5,
        sources,
        calibrations,
      );
    } catch (error) {
      setStepError(messageFromError(
        error,
        "分析設定尚未完成。",
      ));
      return false;
    }

    const payload = buildAnalysisCreatePayload(setup);
    const result = await runMutation(
      "create",
      (signal) => createAnalysisRun(
        payload,
        signal,
      ),
    );
    if (!result) return false;

    const run = normalizeCreatedAnalysisRun(result, {
      record_id: setup.recordId,
      calibration_id: setup.calibrationId,
      method_name: setup.method,
      method_version: setup.method === "top_side_rotating" ? "2.0.0" : "1.0.0",
      status: "draft",
      progress: 0,
      current_frame: 0,
      total_frames: 0,
    });

    if (!run.analysis_id) {
      setMutationError("建立分析的回應缺少分析 ID，結果尚未確認。請返回分析首頁確認狀態，勿立即重送。");
      setMutationRequiresRefresh(true);
      return false;
    }

    setCreatedRun(run);
    setStepError("");
    return true;
  }

  async function validateRun() {
    if (!createdRun?.analysis_id) return false;

    const result = await runMutation(
      "validate",
      (signal) => validateAnalysisRun(
        createdRun.analysis_id,
        signal,
      ),
    );
    if (!result) return false;

    setCreatedRun((previous) => normalizeCreatedAnalysisRun(
      result,
      {
        ...previous,
        status: "ready",
        stage: "validating",
      },
    ));
    return true;
  }

  async function startRun() {
    if (!createdRun?.analysis_id) return false;

    const result = await runMutation(
      "start",
      (signal) => startAnalysisRun(
        createdRun.analysis_id,
        signal,
      ),
    );
    if (!result) return false;

    setCreatedRun((previous) => normalizeCreatedAnalysisRun(
      result,
      {
        ...previous,
        status: "processing",
      },
    ));
    return true;
  }

  return {
    sources,
    calibrations,
    setup,
    currentStep,
    highestStep,
    loading,
    loadError,
    stepError,
    createdRun,
    mutationPending,
    mutationError,
    mutationRequiresRefresh,
    sourceScanning,
    loadOptions,
    selectRecord,
    updateSetup,
    updateCameraSource,
    scanSources,
    updateRoi,
    updateParameter,
    upsertCalibration,
    goToStep,
    nextStep,
    previousStep,
    createRun,
    validateRun,
    startRun,
    clearMutationError: () => setMutationError(""),
  };
}

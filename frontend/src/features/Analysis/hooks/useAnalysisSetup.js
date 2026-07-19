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
  analysisMutationErrorMessage,
  createAnalysisRun,
  loadAnalysisSetupOptions,
  previewAnalysisSources,
  startAnalysisRun,
  validateAnalysisRun,
} from "../lib/analysisApiUtils";
import {
  analysisMethodFromCameraSources,
  analysisSetupFromRecord,
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

function sourceLocationsMatch(
  left,
  right,
) {
  return left?.recordId === right?.recordId
    && ["top", "side", "rotating"].every((cameraId) => (
      left?.cameraSources?.[cameraId]?.path
      === right?.cameraSources?.[cameraId]?.path
    ));
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
  const setupRef = useRef(setup);

  useEffect(() => {
    mountedRef.current = true;

    return () => {
      mountedRef.current = false;
      loadingRef.current = false;
      mutationRef.current = "";
      abortRequest(loadControllerRef.current);
      abortRequest(mutationControllerRef.current);
      abortRequest(sourceScanControllerRef.current);
      loadControllerRef.current = null;
      mutationControllerRef.current = null;
      sourceScanControllerRef.current = null;
    };
  }, []);

  useEffect(() => {
    setupRef.current = setup;
  }, [setup]);

  const performSourceScan = useCallback(async (sourceSetup) => {
    abortRequest(
      sourceScanControllerRef.current,
      "已由新的影像目錄掃描取代。",
    );
    const controller = new AbortController();
    sourceScanControllerRef.current = controller;
    setSourceScanning(true);
    setStepError("");

    try {
      const preview = await previewAnalysisSources(
        {
          record_id: sourceSetup.recordId || null,
          method: sourceSetup.method,
          camera_sources: sourceSetup.cameraSources,
        },
        controller.signal,
      );
      if (!mountedRef.current || controller.signal.aborted) return false;

      setSetup((previous) => {
        if (!sourceLocationsMatch(previous, sourceSetup)) return previous;

        const next = {
          ...previous,
          sourcePreview: preview,
          endFrame: preview?.total_frame_count > 0
            ? String(preview.total_frame_count)
            : previous.endFrame,
        };
        setupRef.current = next;
        return next;
      });
      if (!preview?.ready) {
        setStepError(
          preview?.errors?.[0]
          || "影像目錄尚未具備分析條件。",
        );
      }
      return Boolean(preview?.ready);
    } catch (error) {
      if (error?.name === "AbortError") return false;
      if (mountedRef.current) {
        setStepError(messageFromError(
          error,
          "掃描影像目錄失敗。",
        ));
      }
      return false;
    } finally {
      if (sourceScanControllerRef.current === controller) {
        sourceScanControllerRef.current = null;
        if (mountedRef.current) setSourceScanning(false);
      }
    }
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
      const selectedSource = nextSources.find(
        (source) => source.record_id === setupRef.current.recordId,
      );
      if (selectedSource) {
        const nextSetup = analysisSetupFromRecord(
          setupRef.current,
          selectedSource,
        );
        setupRef.current = nextSetup;
        setSetup(nextSetup);
        void performSourceScan(nextSetup);
      }
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
  }, [performSourceScan]);

  useEffect(() => {
    void loadOptions();
  }, [loadOptions]);

  async function selectRecord(recordId) {
    const source = sources.find((item) => item.record_id === recordId);
    const nextSetup = analysisSetupFromRecord(
      setupRef.current,
      source,
    );
    setupRef.current = nextSetup;
    setSetup(nextSetup);
    setStepError("");

    if (!source) {
      abortRequest(sourceScanControllerRef.current);
      sourceScanControllerRef.current = null;
      setSourceScanning(false);
      return false;
    }

    return performSourceScan(nextSetup);
  }

  function updateSetup(key, value) {
    setSetup((previous) => {
      const next = {
        ...previous,
        [key]: value,
      };
      setupRef.current = next;
      return next;
    });
    setStepError("");
  }

  function updateCameraSource(
    cameraId,
    patch,
  ) {
    const previous = setupRef.current;
    const currentSource = previous.cameraSources[cameraId];
    const pathChanged = Object.hasOwn(patch, "path")
      && patch.path !== currentSource.path;
    const cameraSources = {
      ...previous.cameraSources,
      [cameraId]: {
        ...currentSource,
        ...patch,
      },
    };
    const next = {
      ...previous,
      cameraSources,
      method: analysisMethodFromCameraSources(cameraSources),
      sourcePreview: pathChanged ? null : previous.sourcePreview,
    };
    setupRef.current = next;
    setSetup(next);

    if (pathChanged) {
      abortRequest(sourceScanControllerRef.current);
      sourceScanControllerRef.current = null;
      setSourceScanning(false);
    }
    setStepError("");
  }

  function scanSources() {
    return performSourceScan(setupRef.current);
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

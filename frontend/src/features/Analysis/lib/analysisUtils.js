import {
  ANALYSIS_METHODS,
  ANALYSIS_PARAMETER_DEFAULTS,
  ANALYSIS_STAGE_LABELS,
  ANALYSIS_STATUS_META,
  HIGH_REPROJECTION_ERROR_THRESHOLD_PX,
} from "../analysisConfig.js";

const REQUIRED_PARAMETER_FIELDS = [
  ["segmentationHistory", "背景歷史影格數"],
  ["segmentationVarianceThreshold", "變異門檻"],
  ["segmentationLearningRate", "學習率"],
  ["segmentationInitializationFrames", "背景初始化影格數"],
  ["minimumTopContourArea", "俯視最小輪廓面積"],
  ["minimumSideContourArea", "側視最小輪廓面積"],
  ["lightingChangeArea", "光照切換面積門檻"],
  ["lightingChangeEstimateFrames", "光照穩定等待"],
  ["topPlantBaseX", "俯視植物基部 X"],
  ["topPlantBaseY", "俯視植物基部 Y"],
  ["topSelectedPoints", "俯視候選輪廓數"],
  ["sidePlantBaseX", "側視植物基部 X"],
  ["sidePlantBaseY", "側視植物基部 Y"],
  ["sideSelectedPoints", "側視候選輪廓數"],
  ["maximumEpipolarDistance", "Epipolar 最大距離"],
  ["minimumPathConnectivity", "Minimum Path 鄰接方式"],
  ["maximumInterpolationGapSeconds", "最大插值缺口"],
];

const INTEGER_PARAMETER_FIELDS = new Set([
  "segmentationHistory",
  "segmentationInitializationFrames",
  "openingKernelSize",
  "closingKernelSize",
  "erosionKernelSize",
  "lightingChangeEstimateFrames",
  "topSelectedPoints",
  "topRoiUpdateMargin",
  "sideSelectedPoints",
  "sideRoiUpdateMargin",
  "minimumPathConnectivity",
]);

const NON_NEGATIVE_PARAMETER_FIELDS = new Set([
  "minimumTopContourArea",
  "minimumSideContourArea",
  "lightingChangeArea",
  "topPlantBaseX",
  "topPlantBaseY",
  "topRoiUpdateMargin",
  "sidePlantBaseX",
  "sidePlantBaseY",
  "sideRoiUpdateMargin",
]);

const POSITIVE_PARAMETER_FIELDS = new Set([
  "segmentationHistory",
  "segmentationVarianceThreshold",
  "segmentationInitializationFrames",
  "openingKernelSize",
  "closingKernelSize",
  "erosionKernelSize",
  "lightingChangeEstimateFrames",
  "topSelectedPoints",
  "sideSelectedPoints",
  "maximumEpipolarDistance",
  "maximumInterpolationGapSeconds",
]);

const ODD_KERNEL_FIELDS = [
  "openingKernelSize",
  "closingKernelSize",
  "erosionKernelSize",
];

function arrayFromPayload(
  payload,
  keys,
  label,
) {
  if (Array.isArray(payload)) return payload;

  for (const key of keys) {
    if (Array.isArray(payload?.[key])) return payload[key];
  }

  throw new Error(`${label}資料格式錯誤，請重新讀取。`);
}

function numberOrZero(value) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

function stringOrEmpty(value) {
  return typeof value === "string" ? value : "";
}

function optionalNumber(value) {
  return String(value ?? "").trim() === ""
    ? null
    : Number(value);
}

function normalizeResolution(value) {
  if (!Array.isArray(value) || value.length !== 2) return null;
  const width = Number(value[0]);
  const height = Number(value[1]);
  return Number.isFinite(width)
    && Number.isFinite(height)
    && width > 0
    && height > 0
    ? [width, height]
    : null;
}

function normalizeAnalysisRun(run) {
  return {
    ...run,
    analysis_id: stringOrEmpty(run?.analysis_id),
    record_id: stringOrEmpty(run?.record_id),
    calibration_id: stringOrEmpty(run?.calibration_id),
    status: stringOrEmpty(run?.status) || "draft",
    stage: stringOrEmpty(run?.stage),
    progress: Math.min(1, Math.max(0, numberOrZero(run?.progress))),
    current_frame: Math.max(0, numberOrZero(run?.current_frame)),
    total_frames: Math.max(0, numberOrZero(run?.total_frames)),
    last_error: stringOrEmpty(run?.last_error),
    average_reprojection_error_px: Number.isFinite(Number(
      run?.average_reprojection_error_px
        ?? run?.mean_reprojection_error_px
        ?? run?.reprojection_error_mean_px,
    ))
      ? Number(
        run?.average_reprojection_error_px
          ?? run?.mean_reprojection_error_px
          ?? run?.reprojection_error_mean_px,
      )
      : null,
  };
}

export function analysisSourcesFromPayload(payload) {
  return arrayFromPayload(
    payload,
    ["sources", "records", "items"],
    "可分析紀錄",
  ).map((source) => ({
    ...source,
    record_id: stringOrEmpty(source?.record_id),
    created_at: stringOrEmpty(source?.created_at),
    status: stringOrEmpty(source?.status),
    top_frame_count: Math.max(0, numberOrZero(source?.top_frame_count)),
    side_frame_count: Math.max(0, numberOrZero(source?.side_frame_count)),
    rotating_frame_count: Math.max(
      0,
      numberOrZero(source?.rotating_frame_count),
    ),
    total_frame_count: Math.max(0, numberOrZero(source?.total_frame_count)),
    pairable_frame_count: Math.max(0, numberOrZero(source?.pairable_frame_count)),
    camera_resolutions: {
      top: normalizeResolution(source?.camera_resolutions?.top),
      side: normalizeResolution(source?.camera_resolutions?.side),
      rotating: normalizeResolution(source?.camera_resolutions?.rotating),
    },
    camera_directories: {
      top: stringOrEmpty(source?.camera_directories?.top),
      side: stringOrEmpty(source?.camera_directories?.side),
      rotating: stringOrEmpty(source?.camera_directories?.rotating),
    },
    calibration_status: stringOrEmpty(source?.calibration_status),
    ready: Boolean(source?.ready),
    not_ready_reasons: Array.isArray(source?.not_ready_reasons)
      ? source.not_ready_reasons.filter((reason) => typeof reason === "string")
      : [],
    analysis_runs: Array.isArray(source?.analysis_runs)
      ? source.analysis_runs.map(normalizeAnalysisRun)
      : [],
  }));
}

export function analysisRunsFromPayload(payload) {
  return arrayFromPayload(
    payload,
    ["analysis_runs", "runs", "items"],
    "分析執行",
  ).map(normalizeAnalysisRun);
}

export function calibrationProfilesFromPayload(payload) {
  return arrayFromPayload(
    payload,
    ["calibrations", "profiles", "items"],
    "相機校正",
  ).map((profile) => ({
    ...profile,
    calibration_id: stringOrEmpty(profile?.calibration_id),
    created_at: stringOrEmpty(profile?.created_at),
    status: stringOrEmpty(profile?.status),
    valid: Boolean(profile?.valid),
    potentially_invalid_reasons: Array.isArray(profile?.potentially_invalid_reasons)
      ? profile.potentially_invalid_reasons.filter((reason) => typeof reason === "string")
      : [],
    supports_rotating: Boolean(
      profile?.rotating_camera_matrix
      && profile?.rotating_distortion_coefficients
      && profile?.rotating_axis_origin_mm
      && profile?.rotating_axis_direction
      && profile?.rotating_axis_from_camera_matrix
      && Number.isFinite(Number(profile?.rotating_zero_angle_deg))
      && [-1, 1].includes(Number(profile?.rotating_angle_direction)),
    ),
  }));
}

export function mergeAnalysisRuns(
  sources,
  runs,
) {
  const merged = new Map();

  for (const source of sources) {
    for (const run of source.analysis_runs || []) {
      if (run.analysis_id) merged.set(run.analysis_id, run);
    }
  }

  for (const run of runs) {
    if (run.analysis_id) merged.set(run.analysis_id, run);
  }

  return [...merged.values()].sort((left, right) => (
    String(right.created_at || "").localeCompare(String(left.created_at || ""))
  ));
}

export function mergeAnalysisProgress(
  runs,
  progress,
) {
  const analysisId = stringOrEmpty(progress?.analysis_id);
  if (!analysisId || progress?.status === "idle") return runs;

  let matched = false;
  const nextRuns = runs.map((run) => {
    if (run.analysis_id !== analysisId) return run;
    matched = true;
    return normalizeAnalysisRun({
      ...run,
      status: progress.status,
      stage: progress.stage,
      progress: progress.progress,
      current_frame: progress.current_frame,
      total_frames: progress.total_frames,
      last_error: progress.last_error,
    });
  });

  return matched ? nextRuns : runs;
}

export function analysisStatusMeta(status) {
  return ANALYSIS_STATUS_META[status] || {
    label: status || "未知",
    tone: "neutral",
  };
}

export function analysisStageLabel(stage) {
  return ANALYSIS_STAGE_LABELS[stage] || stage || "尚未開始";
}

export function analysisProgressPercent(progress) {
  return Math.round(Math.min(1, Math.max(0, numberOrZero(progress))) * 100);
}

export function createInitialAnalysisSetup(recordId = "") {
  return {
    recordId,
    method: "top_side",
    cameraSources: {
      top: {
        enabled: true,
        path: "",
      },
      side: {
        enabled: true,
        path: "",
      },
      rotating: {
        enabled: false,
        path: "",
      },
    },
    calibrationId: "",
    startFrame: "1",
    endFrame: "",
    manualFrameOffset: "0",
    topRoi: {
      x: "",
      y: "",
      width: "",
      height: "",
    },
    sideRoi: {
      x: "",
      y: "",
      width: "",
      height: "",
    },
    parameters: {
      ...ANALYSIS_PARAMETER_DEFAULTS,
    },
    manualReviewRequired: true,
  };
}

export function analysisDefaultEndFrame(source) {
  const total = Number(source?.total_frame_count);
  return Number.isInteger(total) && total > 0
    ? String(total)
    : "";
}

function parseRequiredNumber(
  value,
  label,
  {
    integer = false,
    minimum,
    maximum,
    positive = false,
  } = {},
) {
  if (String(value ?? "").trim() === "") {
    throw new Error(`請填寫${label}。`);
  }

  const parsed = Number(value);
  if (!Number.isFinite(parsed) || (integer && !Number.isInteger(parsed))) {
    throw new Error(`${label}必須是${integer ? "整數" : "數值"}。`);
  }
  if (positive && parsed <= 0) {
    throw new Error(`${label}必須大於 0。`);
  }
  if (minimum !== undefined && parsed < minimum) {
    throw new Error(`${label}不可小於 ${minimum}。`);
  }
  if (maximum !== undefined && parsed > maximum) {
    throw new Error(`${label}不可大於 ${maximum}。`);
  }
  return parsed;
}

function parseRoi(
  roi,
  label,
) {
  return {
    x: parseRequiredNumber(roi.x, `${label} X`, {
      integer: true,
      minimum: 0,
    }),
    y: parseRequiredNumber(roi.y, `${label} Y`, {
      integer: true,
      minimum: 0,
    }),
    width: parseRequiredNumber(roi.width, `${label}寬度`, {
      integer: true,
      minimum: 1,
    }),
    height: parseRequiredNumber(roi.height, `${label}高度`, {
      integer: true,
      minimum: 1,
    }),
  };
}

function validateRoiBounds(
  roi,
  label,
  resolution,
) {
  const imageWidth = Number(resolution?.[0]);
  const imageHeight = Number(resolution?.[1]);
  if (
    !Number.isFinite(imageWidth)
    || !Number.isFinite(imageHeight)
    || imageWidth <= 0
    || imageHeight <= 0
  ) {
    return;
  }
  if (
    roi.x + roi.width > imageWidth
    || roi.y + roi.height > imageHeight
  ) {
    throw new Error(`${label} 不可超出 ${imageWidth} × ${imageHeight} 的分析影像範圍。`);
  }
}

export function validateAnalysisSetupStep(
  setup,
  step,
  sources,
  calibrations,
) {
  if (step === 1) {
    const required = setup.method === "top_side_rotating"
      ? ["top", "side", "rotating"]
      : ["top", "side"];
    for (const cameraId of required) {
      const source = setup.cameraSources?.[cameraId];
      if (!source?.enabled) {
        throw new Error(`${ANALYSIS_METHODS[setup.method].label}必須啟用 ${cameraId}。`);
      }
      if (!String(source.path || "").trim()) {
        throw new Error(`請填寫 ${cameraId} 影像目錄。`);
      }
    }
    if (!setup.sourcePreview?.ready) {
      throw new Error(
        setup.sourcePreview?.errors?.[0]
        || "請先掃描影像目錄並確認配對有效。",
      );
    }
    return true;
  }

  if (step === 2) {
    const calibration = calibrations.find(
      (item) => item.calibration_id === setup.calibrationId,
    );
    if (!calibration) throw new Error("請先選擇相機校正。");
    if (!calibration.valid) throw new Error("所選相機校正目前無效，請改選有效校正。");
    if (setup.method === "top_side_rotating" && !calibration.supports_rotating) {
      throw new Error("頂+側+環繞需要包含 rotating 旋轉軸與動態外參的有效校正。");
    }
    return true;
  }

  if (step === 3) {
    const source = setup.sourcePreview;
    const startFrame = parseRequiredNumber(setup.startFrame, "起始影格", {
      integer: true,
      minimum: 1,
    });
    const endFrame = parseRequiredNumber(setup.endFrame, "結束影格", {
      integer: true,
      minimum: 1,
    });
    if (endFrame < startFrame) throw new Error("結束影格不可小於起始影格。");
    if (
      Number.isInteger(source?.total_frame_count)
      && source.total_frame_count > 0
      && endFrame > source.total_frame_count
    ) {
      throw new Error(`結束影格不可超過此紀錄的 ${source.total_frame_count} 組影格。`);
    }
    parseRequiredNumber(setup.manualFrameOffset, "人工影格偏移", {
      integer: true,
    });
    const topRoi = parseRoi(setup.topRoi, "俯視 ROI");
    const sideRoi = parseRoi(setup.sideRoi, "側視 ROI");
    validateRoiBounds(
      topRoi,
      "俯視 ROI",
      source?.camera_resolutions?.top,
    );
    validateRoiBounds(
      sideRoi,
      "側視 ROI",
      source?.camera_resolutions?.side,
    );
    return true;
  }

  if (step === 4) {
    for (const [key, label] of REQUIRED_PARAMETER_FIELDS) {
      const value = setup.parameters[key];
      const minimum = NON_NEGATIVE_PARAMETER_FIELDS.has(key)
          ? 0
          : undefined;
      parseRequiredNumber(value, label, {
        integer: INTEGER_PARAMETER_FIELDS.has(key),
        minimum,
        positive: POSITIVE_PARAMETER_FIELDS.has(key),
      });
    }

    for (const key of ODD_KERNEL_FIELDS) {
      if (String(setup.parameters[key] ?? "").trim() === "") continue;
      parseRequiredNumber(
        setup.parameters[key],
        key === "openingKernelSize"
          ? "開運算核心"
          : key === "closingKernelSize"
            ? "閉運算核心"
            : "侵蝕核心",
        {
          integer: true,
          positive: true,
        },
      );
    }

    if (setup.parameters.topUpdateRoi) {
      parseRequiredNumber(
        setup.parameters.topRoiUpdateMargin,
        "俯視 ROI 更新邊距",
        {
          integer: true,
          minimum: 0,
        },
      );
    }
    if (setup.parameters.sideUpdateRoi) {
      parseRequiredNumber(
        setup.parameters.sideRoiUpdateMargin,
        "側視 ROI 更新邊距",
        {
          integer: true,
          minimum: 0,
        },
      );
    }

    const learningRate = Number(setup.parameters.segmentationLearningRate);
    if (learningRate < -1 || learningRate > 1) {
      throw new Error("學習率必須介於 -1 與 1 之間。");
    }
    for (const key of ODD_KERNEL_FIELDS) {
      const value = optionalNumber(setup.parameters[key]);
      if (value !== null && value % 2 === 0) {
        throw new Error("Morphology 核心大小必須是正奇數。");
      }
    }
    if (![4, 8].includes(Number(setup.parameters.minimumPathConnectivity))) {
      throw new Error("Minimum Path 鄰接方式只能選擇 4 鄰接或 8 鄰接。");
    }
    return true;
  }

  for (const prerequisite of [1, 2, 3, 4]) {
    validateAnalysisSetupStep(
      setup,
      prerequisite,
      sources,
      calibrations,
    );
  }
  return true;
}

export function buildAnalysisCreatePayload(setup) {
  const topRoi = parseRoi(setup.topRoi, "俯視 ROI");
  const sideRoi = parseRoi(setup.sideRoi, "側視 ROI");
  const parameters = setup.parameters;

  return {
    record_id: setup.recordId || null,
    method: setup.method,
    camera_sources: setup.cameraSources,
    calibration_id: setup.calibrationId,
    start_frame: Number(setup.startFrame),
    end_frame: Number(setup.endFrame),
    top_roi: topRoi,
    side_roi: sideRoi,
    manual_frame_offset: Number(setup.manualFrameOffset),
    parameters: {
      method: {
        name: setup.method,
        reference: ANALYSIS_METHODS[setup.method].reference,
      },
      synchronization: {
        primary_key: "cycle_id",
        timestamp_tolerance_ms: 1000,
        manual_frame_offset: Number(setup.manualFrameOffset),
        keep_unpaired_frames: true,
      },
      segmentation: {
        method: "mog2",
        history: Number(parameters.segmentationHistory),
        variance_threshold: Number(parameters.segmentationVarianceThreshold),
        detect_shadows: Boolean(parameters.segmentationDetectShadows),
        learning_rate: Number(parameters.segmentationLearningRate),
        initialization_frames: Number(parameters.segmentationInitializationFrames),
        opening_kernel_size: optionalNumber(parameters.openingKernelSize),
        closing_kernel_size: optionalNumber(parameters.closingKernelSize),
        erosion_kernel_size: optionalNumber(parameters.erosionKernelSize),
        minimum_top_contour_area_px: Number(parameters.minimumTopContourArea),
        minimum_side_contour_area_px: Number(parameters.minimumSideContourArea),
      },
      lighting_change: {
        lighting_change_area_px: Number(parameters.lightingChangeArea),
        lighting_change_est_time_frames: Number(parameters.lightingChangeEstimateFrames),
      },
      top_detection: {
        roi: [topRoi.x, topRoi.y, topRoi.width, topRoi.height],
        plant_base: [
          Number(parameters.topPlantBaseX),
          Number(parameters.topPlantBaseY),
        ],
        num_selected_points: Number(parameters.topSelectedPoints),
        update_roi: Boolean(parameters.topUpdateRoi),
        roi_update_margin_px: parameters.topUpdateRoi
          ? Number(parameters.topRoiUpdateMargin)
          : null,
      },
      side_detection: {
        roi: [sideRoi.x, sideRoi.y, sideRoi.width, sideRoi.height],
        plant_base: [
          Number(parameters.sidePlantBaseX),
          Number(parameters.sidePlantBaseY),
        ],
        num_selected_points: Number(parameters.sideSelectedPoints),
        update_roi: Boolean(parameters.sideUpdateRoi),
        roi_update_margin_px: parameters.sideUpdateRoi
          ? Number(parameters.sideRoiUpdateMargin)
          : null,
        maximum_epipolar_distance_px: Number(parameters.maximumEpipolarDistance),
        minimum_path_connectivity: Number(parameters.minimumPathConnectivity),
        minimum_path_edge_weight: "inverse_distance_transform",
      },
      interpolation: {
        method: "linear",
        maximum_gap_seconds: Number(parameters.maximumInterpolationGapSeconds),
      },
      reprojection: {
        high_error_threshold_px: HIGH_REPROJECTION_ERROR_THRESHOLD_PX,
      },
    },
    manual_review_required: Boolean(setup.manualReviewRequired),
  };
}

export function analysisFrameCount(setup) {
  const start = Number(setup.startFrame);
  const end = Number(setup.endFrame);
  if (!Number.isInteger(start) || !Number.isInteger(end) || end < start) return 0;
  return end - start + 1;
}

export function normalizeCreatedAnalysisRun(
  payload,
  fallback,
) {
  const run = payload?.analysis_run || payload?.run || payload;
  return normalizeAnalysisRun({
    ...fallback,
    ...(run && typeof run === "object" ? run : {}),
  });
}

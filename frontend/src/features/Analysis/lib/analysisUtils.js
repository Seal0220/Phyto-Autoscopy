import { formatDateTime } from "@/lib/formatUtils";

import {
  ANALYSIS_CAMERA_LABELS,
  ANALYSIS_METHODS,
  ANALYSIS_PARAMETER_DEFAULTS,
  ANALYSIS_STAGE_LABELS,
  ANALYSIS_STATUS_META,
} from "../analysisConfig.js";

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
  const poseQuality = run?.pose_quality;

  return {
    ...run,
    analysis_id: stringOrEmpty(run?.analysis_id),
    record_id: stringOrEmpty(run?.record_id),
    status: stringOrEmpty(run?.status) || "draft",
    stage: stringOrEmpty(run?.stage),
    progress: Math.min(1, Math.max(0, numberOrZero(run?.progress))),
    current_frame: Math.max(0, numberOrZero(run?.current_frame)),
    total_frames: Math.max(0, numberOrZero(run?.total_frames)),
    last_error: stringOrEmpty(run?.last_error),
    intrinsics_snapshot: run?.intrinsics_snapshot
      && typeof run.intrinsics_snapshot === "object"
      && !Array.isArray(run.intrinsics_snapshot)
      ? run.intrinsics_snapshot
      : {},
    aruco_layout_snapshot: run?.aruco_layout_snapshot
      && typeof run.aruco_layout_snapshot === "object"
      && !Array.isArray(run.aruco_layout_snapshot)
      ? run.aruco_layout_snapshot
      : {},
    camera_pose_results: Array.isArray(run?.camera_pose_results)
      ? run.camera_pose_results
      : [],
    pose_estimation_version: stringOrEmpty(run?.pose_estimation_version),
    pose_quality: poseQuality
      && typeof poseQuality === "object"
      && !Array.isArray(poseQuality)
      ? poseQuality
      : {},
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
    "紀錄選項",
  ).map((source) => ({
    ...source,
    record_id: stringOrEmpty(source?.record_id),
    record_path: stringOrEmpty(source?.record_path),
    capture_configuration: source?.capture_configuration
      && typeof source.capture_configuration === "object"
      && !Array.isArray(source.capture_configuration)
      ? source.capture_configuration
      : {},
    created_at: stringOrEmpty(source?.created_at),
    ended_at: stringOrEmpty(source?.ended_at),
    status: stringOrEmpty(source?.status),
    top_frame_count: Math.max(0, numberOrZero(source?.top_frame_count)),
    side_frame_count: Math.max(0, numberOrZero(source?.side_frame_count)),
    rotating_frame_count: Math.max(
      0,
      numberOrZero(source?.rotating_frame_count),
    ),
    total_image_count: Math.max(0, numberOrZero(source?.total_image_count)),
    camera_resolutions: {
      top: normalizeResolution(source?.camera_resolutions?.top),
      side: normalizeResolution(source?.camera_resolutions?.side),
      rotating: normalizeResolution(source?.camera_resolutions?.rotating),
    },
    ready: Boolean(source?.ready),
    not_ready_reasons: Array.isArray(source?.not_ready_reasons)
      ? source.not_ready_reasons.filter((reason) => typeof reason === "string")
      : [],
    available_modes: Array.isArray(source?.available_modes)
      ? source.available_modes
        .filter((mode) => mode && typeof mode === "object")
        .map((mode) => ({
          id: stringOrEmpty(mode.id),
          type: stringOrEmpty(mode.type),
          label: stringOrEmpty(mode.label) || stringOrEmpty(mode.type),
          folder: stringOrEmpty(mode.folder),
          storage_scope: stringOrEmpty(mode.storage_scope),
          configuration: mode.configuration
            && typeof mode.configuration === "object"
            && !Array.isArray(mode.configuration)
            ? mode.configuration
            : {},
          image_count: Math.max(0, numberOrZero(mode.image_count)),
        }))
        .filter((mode) => mode.id && mode.folder)
      : [],
    analysis_runs: Array.isArray(source?.analysis_runs)
      ? source.analysis_runs.map(normalizeAnalysisRun)
      : [],
  }));
}

function displayModeNumber(value) {
  const number = Number(value);

  if (!Number.isFinite(number)) return "—";
  return Number.isInteger(number)
    ? String(number)
    : String(Number(number.toFixed(3)));
}

export function analysisModePillLabel(mode) {
  const folder = stringOrEmpty(mode?.folder);
  const label = stringOrEmpty(mode?.label) || folder;
  const modeNumber = folder.match(/\.(\d+)$/)?.[1];

  return modeNumber
    ? `${label} ${modeNumber}`
    : label;
}

export function analysisModeConfigurationLabel(mode) {
  const configuration = mode?.configuration || {};

  if (["continuous_interval", "time_interval"].includes(mode?.type)) {
    return `間隔 ${displayModeNumber(configuration.interval_seconds)} 秒`;
  }
  if (mode?.type === "angle_interval") {
    return `間隔 ${displayModeNumber(configuration.interval_degrees)} 度`;
  }
  if (mode?.type === "specific_angles") {
    const angles = Array.isArray(configuration.angles)
      ? configuration.angles
      : String(configuration.angles || "")
        .split(",")
        .map((angle) => angle.trim())
        .filter(Boolean);

    return angles.length > 0
      ? `角度 ${angles.map(displayModeNumber).join("、")} 度`
      : "角度尚無資料";
  }
  if (mode?.type === "equal_divisions") {
    return `等分 ${displayModeNumber(configuration.points)} 點`;
  }
  return "配置尚無資料";
}

export function analysisDefaultSelectedModeIds(modes) {
  return (Array.isArray(modes) ? modes : [])
    .filter((mode) => mode?.type !== "continuous_interval")
    .map((mode) => mode.id);
}

export function analysisRunsFromPayload(payload) {
  return arrayFromPayload(
    payload,
    ["analysis_runs", "runs", "items"],
    "分析紀錄",
  ).map(normalizeAnalysisRun);
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
    label: "未知狀態",
    tone: "neutral",
  };
}

export function analysisStageLabel(stage) {
  if (!stage) return "尚未開始";
  return ANALYSIS_STAGE_LABELS[stage] || "未知階段";
}

export function analysisRecordSummaryItems(source) {
  const modeCount = Array.isArray(source?.available_modes)
    ? source.available_modes.length
    : 0;
  const totalImageCount = Math.max(
    0,
    numberOrZero(source?.total_image_count),
  );

  return [
    {
      label: "開始時間",
      value: formatDateTime(source?.created_at),
    },
    {
      label: "結束時間",
      value: source?.ended_at
        ? formatDateTime(source.ended_at)
        : "尚未結束",
    },
    {
      label: "模式數量",
      value: `${modeCount} 種`,
    },
    {
      label: "總張數",
      value: `${totalImageCount} 張`,
    },
  ];
}

export function analysisProgressPercent(progress) {
  return Math.round(Math.min(1, Math.max(0, numberOrZero(progress))) * 100);
}

export function createInitialAnalysisSetup(recordId = "") {
  return {
    recordId,
    recordPath: "",
    captureConfiguration: {},
    availableModes: [],
    selectedModeIds: [],
    method: "rotating",
    cameraSources: {
      top: {
        enabled: true,
      },
      side: {
        enabled: true,
      },
      rotating: {
        enabled: true,
      },
    },
    parameters: {
      ...ANALYSIS_PARAMETER_DEFAULTS,
    },
    manualReviewRequired: true,
  };
}

export function analysisMethodFromCameraSources(cameraSources) {
  return cameraSources?.rotating?.enabled
    ? "rotating"
    : "fixed";
}

export function analysisCameraSourceRequired(cameraId) {
  return cameraId === "top" || cameraId === "side";
}

export function analysisSetupFromRecord(
  setup,
  source,
) {
  const cameraSources = {
    top: {
      enabled: true,
    },
    side: {
      enabled: true,
    },
    rotating: {
      enabled: true,
    },
  };
  const availableModes = Array.isArray(source?.available_modes)
    ? source.available_modes
    : [];

  return {
    ...setup,
    recordId: stringOrEmpty(source?.record_id),
    recordPath: stringOrEmpty(source?.record_path),
    captureConfiguration: source?.capture_configuration
      && typeof source.capture_configuration === "object"
      && !Array.isArray(source.capture_configuration)
      ? source.capture_configuration
      : {},
    method: analysisMethodFromCameraSources(cameraSources),
    availableModes,
    selectedModeIds: analysisDefaultSelectedModeIds(availableModes),
    cameraSources,
    sourcePreview: null,
  };
}

export function analysisCameraSourcesPayload(setup) {
  return Object.fromEntries(
    Object.entries(setup.cameraSources).map(([cameraId, source]) => [
      cameraId,
      {
        enabled: analysisCameraSourceRequired(cameraId)
          || Boolean(source.enabled),
        path: setup.recordPath,
      },
    ]),
  );
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

export function validateAnalysisSetupStep(
  setup,
  step,
) {
  if (step === 1) {
    if (!setup.recordId) {
      throw new Error("請先選擇一筆紀錄。");
    }
    if (!String(setup.recordPath || "").trim()) {
      throw new Error("所選紀錄缺少根目錄。");
    }
    return true;
  }

  if (step === 2) {
    if (
      setup.recordId
      && setup.availableModes.length > 0
      && setup.selectedModeIds.length === 0
    ) {
      throw new Error("請至少選擇一個擷取模式。");
    }
    const required = setup.method === "rotating"
      ? ["top", "side", "rotating"]
      : ["top", "side"];
    for (const cameraId of required) {
      const source = setup.cameraSources?.[cameraId];
      if (!source?.enabled) {
        throw new Error(
          `${ANALYSIS_METHODS[setup.method].label}必須啟用`
          + `${ANALYSIS_CAMERA_LABELS[cameraId]}。`,
        );
      }
    }
    if (!setup.sourcePreview?.ready) {
      throw new Error(
        setup.sourcePreview?.errors?.[0]
        || "請先掃描捕捉配置並確認 Round 資料有效。",
      );
    }
    if (
      setup.method === "rotating"
      && Number(setup.sourcePreview.ready_round_count) <= 0
    ) {
      throw new Error("請重新掃描並確認至少有一個可用的多視角 Round。");
    }
    return true;
  }

  if (step === 3) {
    if (!setup.parameters.generatePlantMask) {
      throw new Error("分析必須建立植物遮罩。");
    }
    parseRequiredNumber(
      setup.parameters.minimumTipConfidence,
      "最低尖端標記信心",
      {
        minimum: 0,
        maximum: 1,
      },
    );
    parseRequiredNumber(
      setup.parameters.minimumSupportingViews,
      "最低支持視角數",
      {
        integer: true,
        minimum: 2,
      },
    );
    parseRequiredNumber(
      setup.parameters.maximumTipReprojectionError,
      "最大重投影誤差",
      {
        positive: true,
      },
    );
    if (
      setup.method === "rotating"
      && !["preview", "standard", "high"].includes(
        setup.parameters.qualityPreset,
      )
    ) {
      throw new Error("請選擇有效的模型品質。");
    }
    return true;
  }

  for (const prerequisite of [1, 2, 3]) {
    validateAnalysisSetupStep(
      setup,
      prerequisite,
    );
  }
  for (const [cameraId, source] of Object.entries(setup.cameraSources)) {
    if (!source.enabled) continue;
    if (!setup.sourcePreview?.intrinsics_readiness?.[cameraId]?.ready) {
      throw new Error(
        `${ANALYSIS_CAMERA_LABELS[cameraId] || "相機"}`
        + "尚未建立可用的內部參數。",
      );
    }
  }
  if (!setup.sourcePreview?.aruco_readiness?.ready) {
    throw new Error("ArUco 世界座標基準尚未就緒。");
  }
  if (
    setup.method === "rotating"
    && !setup.sourcePreview?.backend_readiness?.available
  ) {
    throw new Error(
      setup.sourcePreview?.backend_readiness?.errors?.[0]
      || "目前沒有可用的三維模型建立後端。",
    );
  }
  return true;
}

export function buildAnalysisCreatePayload(setup) {
  const parameters = setup.parameters;
  const buildsRoundModels = setup.method === "rotating";

  return {
    record_id: setup.recordId,
    mode_ids: setup.selectedModeIds,
    method: setup.method,
    camera_sources: analysisCameraSourcesPayload(setup),
    parameters: {
      reconstruction: {
        backend: parameters.reconstructionBackend,
        quality_preset: parameters.qualityPreset,
        save_checkpoint: Boolean(parameters.saveCheckpoints),
        export_gaussians: buildsRoundModels
          && Boolean(parameters.saveGaussianModel)
          && Boolean(parameters.preserveSceneModel),
        export_plant_gaussians: buildsRoundModels
          && Boolean(parameters.saveGaussianModel)
          && Boolean(parameters.exportPlantModel),
        export_background_gaussians: buildsRoundModels
          && Boolean(parameters.saveGaussianModel)
          && Boolean(parameters.saveBackgroundModel),
        export_point_cloud: buildsRoundModels
          && Boolean(parameters.exportScenePointCloud),
        export_plant_point_cloud: buildsRoundModels
          && Boolean(parameters.exportPlantPointCloud),
        export_render_preview: buildsRoundModels
          && Boolean(parameters.saveModelPreviews),
        use_pose_refinement: buildsRoundModels
          && Boolean(parameters.useBundleAdjustment),
        use_plant_mask: buildsRoundModels
          && Boolean(parameters.usePlantMaskInLoss),
      },
      pose_strategy: {
        use_aruco_world_pose: true,
        use_bundle_adjustment: buildsRoundModels
          && Boolean(parameters.useBundleAdjustment),
      },
      background: {
        generate_plant_mask: Boolean(parameters.generatePlantMask),
        use_plant_mask_in_loss: buildsRoundModels
          && Boolean(parameters.usePlantMaskInLoss),
        preserve_scene_model: buildsRoundModels
          && Boolean(parameters.preserveSceneModel),
        export_plant_model: buildsRoundModels
          && Boolean(parameters.exportPlantModel),
        save_background_model: buildsRoundModels
          && Boolean(parameters.saveBackgroundModel),
      },
      tip_analysis: {
        minimum_confidence: Number(parameters.minimumTipConfidence),
        minimum_supporting_views: Number(parameters.minimumSupportingViews),
        maximum_reprojection_error_px: Number(
          parameters.maximumTipReprojectionError,
        ),
        use_skeleton_refinement: buildsRoundModels
          && Boolean(parameters.useSkeletonRefinement),
        use_temporal_prior: Boolean(parameters.useTemporalPrior),
        wait_for_low_confidence_review: Boolean(
          parameters.waitForLowConfidenceReview,
        ),
        export_all_2d_candidates: Boolean(parameters.exportAll2dCandidates),
        save_reprojection_overlays: Boolean(
          parameters.saveReprojectionOverlays,
        ),
      },
      outputs: {
        save_gaussian_model: buildsRoundModels
          && Boolean(parameters.saveGaussianModel),
        export_scene_point_cloud: buildsRoundModels
          && Boolean(parameters.exportScenePointCloud),
        export_plant_point_cloud: buildsRoundModels
          && Boolean(parameters.exportPlantPointCloud),
        export_skeleton: buildsRoundModels
          && Boolean(parameters.exportSkeleton),
        export_tip_markers: Boolean(parameters.exportTipMarkers),
        export_trajectory_csv: Boolean(parameters.exportTrajectoryCsv),
        save_model_previews: buildsRoundModels
          && Boolean(parameters.saveModelPreviews),
        save_diagnostics: Boolean(parameters.saveDiagnostics),
        save_checkpoints: buildsRoundModels
          && Boolean(parameters.saveCheckpoints),
      },
    },
    manual_review_required: Boolean(setup.manualReviewRequired),
  };
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

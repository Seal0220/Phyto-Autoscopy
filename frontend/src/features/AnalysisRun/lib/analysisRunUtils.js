import {
  ANALYSIS_CAMERA_LABELS,
  ANALYSIS_STAGE_LABELS,
  ANALYSIS_STATUS_META,
} from "../../Analysis/analysisConfig.js";
import {
  ANALYSIS_PROGRESS_UNITS,
  ANALYSIS_VALIDATION_STAGES,
} from "../analysisRunConfig.js";
import { needsStereoPoseReview } from "./analysisStereoReviewUtils.js";

const ACTIVE_STATUSES = new Set([
  "validating",
  "processing",
  "reconstructing",
  "pausing",
]);

const ROUND_STATUS_META = {
  ready: {
    label: "等待處理",
    tone: "neutral",
  },
  ready_tip_only: {
    label: "等待尖端分析",
    tone: "neutral",
  },
  preprocessed: {
    label: "影像已處理",
    tone: "warning",
  },
  reconstructing: {
    label: "模型建立中",
    tone: "warning",
  },
  model_completed: {
    label: "模型已完成",
    tone: "success",
  },
  model_failed: {
    label: "模型失敗",
    tone: "offline",
  },
  tip_completed: {
    label: "分析完成",
    tone: "success",
  },
  tip_only: {
    label: "僅尖端標記",
    tone: "warning",
  },
  tip_invalid: {
    label: "尖端待補正",
    tone: "warning",
  },
  failed: {
    label: "處理失敗",
    tone: "offline",
  },
  cancelled: {
    label: "已取消",
    tone: "neutral",
  },
};

function finiteNumber(
  value,
  fallback = 0,
) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function text(value) {
  return typeof value === "string" ? value : "";
}

export function normalizeAnalysisRun(payload) {
  return {
    ...(payload && typeof payload === "object" ? payload : {}),
    analysis_id: text(payload?.analysis_id),
    record_id: text(payload?.record_id),
    method_name: text(payload?.method_name),
    method_version: text(payload?.method_version),
    git_commit: text(payload?.git_commit),
    created_by: text(payload?.created_by),
    created_at: text(payload?.created_at),
    updated_at: text(payload?.updated_at),
    output_path: text(payload?.output_path),
    status: text(payload?.status) || "draft",
    stage: text(payload?.stage),
    progress: Math.min(1, Math.max(0, finiteNumber(payload?.progress))),
    current_frame: Math.max(0, finiteNumber(payload?.current_frame)),
    total_frames: Math.max(0, finiteNumber(payload?.total_frames)),
    manual_review_completed: Boolean(payload?.manual_review_completed),
    last_error: text(payload?.last_error),
    parameters: payload?.parameters && typeof payload.parameters === "object"
      ? payload.parameters
      : {},
  };
}

export function normalizeAnalysisProgress(payload) {
  return {
    analysis_id: text(payload?.analysis_id),
    status: text(payload?.status) || "idle",
    stage: text(payload?.stage),
    current_frame: Math.max(0, finiteNumber(payload?.current_frame)),
    total_frames: Math.max(0, finiteNumber(payload?.total_frames)),
    progress: Math.min(1, Math.max(0, finiteNumber(payload?.progress))),
    round_key: text(payload?.round_key),
    round_id: text(payload?.round_id),
    current_round: Math.max(0, finiteNumber(payload?.current_round)),
    total_rounds: Math.max(0, finiteNumber(payload?.total_rounds)),
    round_progress: Math.min(1, Math.max(0, finiteNumber(payload?.round_progress))),
    last_error: text(payload?.last_error),
    processing_preview: payload?.processing_preview
      && typeof payload.processing_preview === "object"
      ? payload.processing_preview
      : null,
    image_probe_backends: payload?.image_probe_backends
      && typeof payload.image_probe_backends === "object"
      ? payload.image_probe_backends
      : {},
    checkpoints: payload?.checkpoints && typeof payload.checkpoints === "object"
      ? payload.checkpoints
      : { completed_steps: 0, recent_steps: [] },
  };
}

export function analysisImageGroups(views) {
  const groups = new Map();
  for (const view of Array.isArray(views) ? views : []) {
    const key = view.snapshot_id || view.timestamp || view.view_id;
    if (!groups.has(key)) groups.set(key, { key, views: [] });
    groups.get(key).views.push(view);
  }
  const cameraOrder = Object.keys(ANALYSIS_CAMERA_LABELS);
  for (const group of groups.values()) {
    group.views.sort((first, second) => {
      const firstIndex = cameraOrder.indexOf(first.camera_id);
      const secondIndex = cameraOrder.indexOf(second.camera_id);
      return (firstIndex < 0 ? cameraOrder.length : firstIndex)
        - (secondIndex < 0 ? cameraOrder.length : secondIndex);
    });
  }
  return [...groups.values()];
}

export function analysisRoundStatus(status) {
  return ROUND_STATUS_META[text(status)] || {
    label: text(status) ? "未知狀態" : "尚未處理",
    tone: "neutral",
  };
}

export function analysisRunDisplay(run) {
  const status = ANALYSIS_STATUS_META[run?.status] || {
    label: run?.status ? "未知狀態" : "尚未開始",
    tone: "neutral",
  };
  const probeCounts = run?.image_probe_backends || run?.parameters?.validation_image_probe_backends;
  const validating = run?.status === "validating" || ANALYSIS_VALIDATION_STAGES.has(run?.stage);
  const workerNote = finiteNumber(probeCounts?.workers) > 0
    ? `自動並行 ${finiteNumber(probeCounts.workers)} 執行緒${probeCounts.tuning ? `（試速中，上限 ${finiteNumber(probeCounts.worker_limit)}）` : ""}`
    : "";
  const backendNote = probeCounts && (finiteNumber(probeCounts.gpu) + finiteNumber(probeCounts.cpu) + finiteNumber(probeCounts.reused)) > 0
    ? probeCounts.remap_gpu !== undefined
      ? `GPU 去畸變 ${finiteNumber(probeCounts.remap_gpu) + finiteNumber(probeCounts.reused_gpu)} 張 · CPU 去畸變 ${finiteNumber(probeCounts.remap_cpu) + finiteNumber(probeCounts.reused_cpu)} 張 · 沿用已完成影像 ${finiteNumber(probeCounts.reused)} 張`
      : `轉檔 ${finiteNumber(probeCounts.converted)} 張 · GPU ${finiteNumber(probeCounts.gpu)} 張 · CPU 回退 ${finiteNumber(probeCounts.cpu)} 張`
    : "";
  const roundNote = finiteNumber(run?.total_rounds) > 0
    ? `第 ${finiteNumber(run.current_round)} / ${finiteNumber(run.total_rounds)} 輪${run.round_id ? `（${run.round_id}）` : ""}`
    : "";
  const stepNote = finiteNumber(run?.total_frames) > 0
    ? `${finiteNumber(run.current_frame)} / ${finiteNumber(run.total_frames)} ${ANALYSIS_PROGRESS_UNITS[run.stage] || "輪"}`
    : "準備中…";

  return {
    status,
    probeNote: [workerNote, backendNote].filter(Boolean).join(" · "),
    progressTitle: validating
      ? "驗證進度"
      : "分析進度",
    progressNote: [roundNote, stepNote].filter(Boolean).join(" · "),
    stage: ANALYSIS_STAGE_LABELS[run?.stage]
      || (run?.stage ? "未知階段" : "尚未開始"),
    progressPercent: Math.round(
      Math.min(1, Math.max(0, finiteNumber(run?.progress))) * 100,
    ),
  };
}

export function analysisRunActionAvailability(
  status,
  stage,
  hasResults = false,
) {
  const stereoReview = needsStereoPoseReview({ status, stage });
  return {
    validate: status === "draft",
    start: status === "ready",
    cancel: ACTIVE_STATUSES.has(status),
    pause: ACTIVE_STATUSES.has(status) && status !== "pausing",
    resume: status === "paused",
    retry: ["failed", "cancelled"].includes(status),
    rebuildPreview: ["needs_review", "reviewing"].includes(status) && stage === "waiting_for_model_review",
    reset: ["failed", "cancelled", "paused"].includes(status),
    review: stereoReview || [
      "needs_review",
      "reviewing",
      "completed",
      "partially_completed",
    ].includes(status),
    skipReview: !stereoReview && ["needs_review", "reviewing"].includes(status),
    results: hasResults || ["completed", "partially_completed"].includes(status),
    export: ["completed", "partially_completed"].includes(status),
  };
}

export function analysisRunActionRequest(action) {
  if (action === "reconstruct_without_review") {
    return {
      action: "reconstruct",
      body: {
        manual_review_completed: false,
      },
    };
  }

  return {
    action,
    body: {},
  };
}

export function analysisInputCount(run) {
  return Array.isArray(run?.parameters?.input_manifest)
    ? run.parameters.input_manifest.length
    : finiteNumber(run?.parameters?.input_count);
}

export function formatAnalysisTimestamp(value) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? String(value)
    : new Intl.DateTimeFormat("zh-TW", {
      dateStyle: "medium",
      timeStyle: "medium",
    }).format(date);
}

export function truncateCommit(value) {
  const commit = text(value);
  return commit && commit !== "unknown"
    ? commit.slice(0, 12)
    : "未知";
}

export function isValidAnalysisId(value) {
  return typeof value === "string"
    && value.length >= 1
    && value.length <= 160
    && /^[A-Za-z0-9._-]+$/.test(value);
}

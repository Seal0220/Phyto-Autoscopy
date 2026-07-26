import {
  ANALYSIS_STAGE_LABELS,
  ANALYSIS_STATUS_META,
} from "../../Analysis/analysisConfig.js";

const ACTIVE_STATUSES = new Set([
  "validating",
  "processing",
  "reconstructing",
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
    label: "尖端不可確認",
    tone: "offline",
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
    last_error: text(payload?.last_error),
  };
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

  return {
    status,
    stage: ANALYSIS_STAGE_LABELS[run?.stage]
      || (run?.stage ? "未知階段" : "尚未開始"),
    progressPercent: Math.round(
      Math.min(1, Math.max(0, finiteNumber(run?.progress))) * 100,
    ),
  };
}

export function analysisRunActionAvailability(
  status,
) {
  return {
    validate: status === "draft",
    start: status === "ready",
    cancel: ACTIVE_STATUSES.has(status),
    retry: ["failed", "cancelled"].includes(status),
    reset: ["failed", "cancelled"].includes(status),
    review: [
      "needs_review",
      "reviewing",
      "completed",
      "partially_completed",
    ].includes(status),
    skipReview: ["needs_review", "reviewing"].includes(status),
    results: ["completed", "partially_completed"].includes(status),
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
    : 0;
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

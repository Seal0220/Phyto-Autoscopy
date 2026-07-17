import {
  ANALYSIS_STAGE_LABELS,
  ANALYSIS_STATUS_META,
} from "../../Analysis/analysisConfig.js";

const ACTIVE_STATUSES = new Set([
  "validating",
  "processing",
  "reconstructing",
]);

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
    calibration_id: text(payload?.calibration_id),
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

export function normalizeFramePairs(payload) {
  const items = Array.isArray(payload)
    ? payload
    : Array.isArray(payload?.items)
      ? payload.items
      : [];

  return items.map((item) => ({
    ...item,
    frame_id: Math.max(0, finiteNumber(item?.frame_id)),
    pair_status: text(item?.pair_status) || "unknown",
  }));
}

export function analysisRunDisplay(run) {
  const status = ANALYSIS_STATUS_META[run?.status] || {
    label: run?.status || "未知",
    tone: "neutral",
  };

  return {
    status,
    stage: ANALYSIS_STAGE_LABELS[run?.stage] || run?.stage || "尚未開始",
    progressPercent: Math.round(
      Math.min(1, Math.max(0, finiteNumber(run?.progress))) * 100,
    ),
  };
}

export function analysisRunActionAvailability(status) {
  return {
    validate: status === "draft",
    start: status === "ready",
    cancel: ACTIVE_STATUSES.has(status),
    retry: ["failed", "cancelled"].includes(status),
    reset: ["failed", "cancelled"].includes(status),
    review: ["needs_review", "reviewing", "completed"].includes(status),
    skipReview: ["needs_review", "reviewing"].includes(status),
    results: status === "completed",
    export: status === "completed",
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

export function framePairCounts(framePairs) {
  const counts = {
    paired: 0,
    manuallyAligned: 0,
    unresolved: 0,
  };

  for (const pair of framePairs || []) {
    if (pair.pair_status === "paired") counts.paired += 1;
    else if (pair.pair_status === "manually_aligned") {
      counts.manuallyAligned += 1;
    } else counts.unresolved += 1;
  }

  return counts;
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

export {
  epipolarSegment,
  pointInsideImage,
} from "../../../lib/imageGeometryUtils.js";

function finiteNumber(value) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

export function normalizePoint(value) {
  if (!value || typeof value !== "object") return null;
  const x = finiteNumber(value.x_px ?? value.x);
  const y = finiteNumber(value.y_px ?? value.y);
  return x === null || y === null
    ? null
    : {
      x,
      y,
    };
}

function normalizePointList(value) {
  return Array.isArray(value)
    ? value.map(normalizePoint).filter(Boolean)
    : [];
}

function normalizeContour(value) {
  return Array.isArray(value)
    ? value.map((point) => {
      if (Array.isArray(point) && point.length >= 2) {
        const x = finiteNumber(point[0]);
        const y = finiteNumber(point[1]);
        return x === null || y === null ? null : { x, y };
      }
      return normalizePoint(point);
    }).filter(Boolean)
    : [];
}

export function normalizeDetection(value) {
  if (!value || typeof value !== "object") return null;
  return {
    ...value,
    selectedPoint: normalizePoint(value.selected_point),
    candidatePoints: normalizePointList(value.candidate_points),
    contour: normalizeContour(value.contour),
    minimumPath: normalizePointList(value.minimum_path),
    epipolarLine: Array.isArray(value.epipolar_line)
      ? value.epipolar_line.map(Number).slice(0, 3)
      : null,
    detectionType: typeof value.detection_type === "string"
      ? value.detection_type
      : "Missing",
    valid: Boolean(value.valid),
    statusReason: typeof value.status_reason === "string"
      ? value.status_reason
      : "",
  };
}

export function normalizeStoredDetection(value) {
  if (!value || typeof value !== "object") return null;
  return {
    automatic: normalizeDetection(value.automatic_detection),
    interpolated: normalizeDetection(value.interpolated_detection),
    resolved: normalizeDetection(value.resolved_detection),
  };
}

export function normalizeCorrection(value) {
  if (!value || typeof value !== "object") return null;
  return {
    ...value,
    correction_id: typeof value.correction_id === "string"
      ? value.correction_id
      : "",
    camera_id: value.camera_id === "side" ? "side" : "top",
    frame_id: Number(value.frame_id),
    correctedPoint: value.invalid
      ? null
      : normalizePoint({
        x_px: value.corrected_x_px,
        y_px: value.corrected_y_px,
      }),
    invalid: Boolean(value.invalid),
    reason: typeof value.reason === "string" ? value.reason : "",
    operator_id: typeof value.operator_id === "string"
      ? value.operator_id
      : "",
    created_at: typeof value.created_at === "string"
      ? value.created_at
      : "",
  };
}

export function normalizeFrameDetail(value) {
  const frameId = Number(value?.pair?.frame_id);
  return {
    pair: {
      ...(value?.pair || {}),
      frame_id: Number.isFinite(frameId) ? frameId : 0,
    },
    topImageUrl: typeof value?.top_image_url === "string"
      ? value.top_image_url
      : "",
    sideImageUrl: typeof value?.side_image_url === "string"
      ? value.side_image_url
      : "",
    topDetection: normalizeStoredDetection(value?.top_detection),
    sideDetection: normalizeStoredDetection(value?.side_detection),
    corrections: Array.isArray(value?.corrections)
      ? value.corrections.map(normalizeCorrection).filter(Boolean)
      : [],
  };
}

export function normalizedFrameIds(framePairs) {
  return (Array.isArray(framePairs) ? framePairs : [])
    .map((pair) => Number(pair?.frame_id))
    .filter((frameId) => Number.isInteger(frameId) && frameId >= 0)
    .sort((
      left,
      right,
    ) => left - right);
}

export function latestCorrection(
  corrections,
  cameraId,
) {
  return [...(corrections || [])]
    .filter((correction) => correction.camera_id === cameraId)
    .sort((
      left,
      right,
    ) => (
      String(left.created_at).localeCompare(String(right.created_at))
    ))
    .at(-1) || null;
}

export function initialCorrectionDraft(
  storedDetection,
  corrections,
  cameraId,
) {
  const latest = latestCorrection(corrections, cameraId);
  const finalPoint = latest
    ? latest.invalid
      ? null
      : latest.correctedPoint
    : storedDetection?.resolved?.selectedPoint
      || storedDetection?.interpolated?.selectedPoint
      || storedDetection?.automatic?.selectedPoint
      || null;

  return {
    point: finalPoint,
    invalid: Boolean(latest?.invalid),
    reason: latest?.reason || "",
    dirty: false,
  };
}

export function correctionPayload(
  frameId,
  cameraId,
  draft,
) {
  if (!draft?.invalid && !draft?.point) {
    throw new Error("請先在影像上指定尖端位置，或將此相機影格標記為無效。");
  }

  return {
    frame_id: frameId,
    camera_id: cameraId,
    corrected_x_px: draft.invalid ? null : draft.point.x,
    corrected_y_px: draft.invalid ? null : draft.point.y,
    reason: String(draft.reason || "").trim() || null,
    invalid: Boolean(draft.invalid),
  };
}

export function formatTipTimestamp(value) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? String(value)
    : new Intl.DateTimeFormat("zh-TW", {
      dateStyle: "short",
      timeStyle: "medium",
    }).format(date);
}

export function framePairStatusLabel(status) {
  return {
    paired: "已配對",
    manually_aligned: "人工偏移配對",
    top_missing: "缺少俯視影格",
    side_missing: "缺少側視影格",
    outside_tolerance: "超出時間容許範圍",
  }[status] || "未知";
}

export function detectionTypeLabel(type) {
  return {
    Automatic: "自動",
    Estimated: "估計",
    Interpolated: "插值",
    Manual: "人工",
    Missing: "缺失",
    Invalid: "無效",
    background_initialization: "背景初始化",
    lighting_transition: "光照切換等待",
  }[type] || "缺失";
}

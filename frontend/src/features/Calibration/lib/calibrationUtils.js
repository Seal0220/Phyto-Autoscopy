import {
  CALIBRATION_BOARD_DEFAULTS,
  CALIBRATION_PAPER_SIZE_OPTIONS,
  CALIBRATION_SUGGESTED_ANGLES,
} from "../calibrationConfig.js";

export function calibrationBoardMetrics({
  paperSize,
  paperOrientation,
  squaresX,
  squaresY,
}) {
  const paper = CALIBRATION_PAPER_SIZE_OPTIONS.find(
    (option) => option.value === paperSize,
  ) || CALIBRATION_PAPER_SIZE_OPTIONS.find(
    (option) => option.value === CALIBRATION_BOARD_DEFAULTS.paperSize,
  );
  const landscape = paperOrientation === "landscape";
  const pageWidthMm = landscape
    ? Math.max(paper.widthMm, paper.heightMm)
    : Math.min(paper.widthMm, paper.heightMm);
  const pageHeightMm = landscape
    ? Math.min(paper.widthMm, paper.heightMm)
    : Math.max(paper.widthMm, paper.heightMm);
  const printableWidthMm = pageWidthMm - CALIBRATION_BOARD_DEFAULTS.printMarginMm * 2;
  const printableHeightMm = pageHeightMm - CALIBRATION_BOARD_DEFAULTS.printMarginMm * 2;
  const columns = Math.max(3, Number(squaresX) || 3);
  const rows = Math.max(3, Number(squaresY) || 3);
  const squareLengthMm = Math.min(
    printableWidthMm / columns,
    printableHeightMm / rows,
  );

  return {
    pageWidthMm,
    pageHeightMm,
    printableWidthMm,
    printableHeightMm,
    squareLengthMm,
    markerLengthMm: squareLengthMm
      * CALIBRATION_BOARD_DEFAULTS.markerToSquareRatio,
  };
}

export function calibrationLockState(
  status,
  localOwnership = false,
) {
  const ownsLock = Boolean(
    localOwnership
    || status?.lock_owned_by_requester,
  );
  return {
    ownsLock,
    lockedByAnotherOperator: Boolean(status?.lock?.locked) && !ownsLock,
  };
}

export function suggestedCalibrationAngles(range) {
  const minimum = Number(range?.[0]);
  const maximum = Number(range?.[1]);
  if (!Number.isFinite(minimum) || !Number.isFinite(maximum)) {
    return [...CALIBRATION_SUGGESTED_ANGLES];
  }
  return CALIBRATION_SUGGESTED_ANGLES.filter((angle) => (
    angle >= minimum && angle <= maximum
  ));
}

export function calibrationAngleCompleted(
  observations,
  angle,
  tolerance = 0.5,
) {
  return (observations || []).some((observation) => {
    if (observation?.motor_angle_deg === null
      || observation?.motor_angle_deg === undefined) {
      return false;
    }
    const observedAngle = Number(observation.motor_angle_deg);
    return observation.accepted
      && observation.detections?.rotating?.board_detected
      && Number.isFinite(observedAngle)
      && Math.abs(observedAngle - angle) < tolerance;
  });
}

export function intrinsicCaptureNotice(
  cameraLabel,
  run,
) {
  const sample = Array.isArray(run?.samples)
    ? run.samples.at(-1)
    : null;
  if (!sample) return null;
  return sample.accepted
    ? {
      message: `${cameraLabel}已接受新的內參樣本。`,
      tone: "success",
    }
    : {
      message: `${cameraLabel}樣本未儲存：${sample.rejection_reason || "影像未達擷取條件。"}`,
      tone: "warning",
    };
}

const INTRINSIC_COVERAGE_CELLS = Object.freeze([
  Object.freeze({
    column: 0,
    row: 0,
    label: "左上",
    edge: true,
  }),
  Object.freeze({
    column: 1,
    row: 0,
    label: "上方",
    edge: true,
  }),
  Object.freeze({
    column: 2,
    row: 0,
    label: "右上",
    edge: true,
  }),
  Object.freeze({
    column: 0,
    row: 1,
    label: "左側",
    edge: true,
  }),
  Object.freeze({
    column: 1,
    row: 1,
    label: "中央",
    edge: false,
  }),
  Object.freeze({
    column: 2,
    row: 1,
    label: "右側",
    edge: true,
  }),
  Object.freeze({
    column: 0,
    row: 2,
    label: "左下",
    edge: true,
  }),
  Object.freeze({
    column: 1,
    row: 2,
    label: "下方",
    edge: true,
  }),
  Object.freeze({
    column: 2,
    row: 2,
    label: "右下",
    edge: true,
  }),
]);

function finiteNumber(
  value,
  fallback = 0,
) {
  const number = Number(value);
  return Number.isFinite(number) ? number : fallback;
}

function normalizedBoardCenter(sample) {
  const x = Number(sample?.board_center?.[0]);
  const y = Number(sample?.board_center?.[1]);
  if (!Number.isFinite(x) || !Number.isFinite(y)) return null;
  return {
    id: sample.sample_id,
    x: Math.min(1, Math.max(0, x)),
    y: Math.min(1, Math.max(0, y)),
  };
}

export function intrinsicCoverageSummary(run) {
  const coverage = run?.coverage || {};
  const acceptedSamples = (run?.samples || []).filter(
    (sample) => sample.accepted,
  );
  const points = acceptedSamples
    .map(normalizedBoardCenter)
    .filter(Boolean);
  const occupiedKeys = new Set(points.map((point) => {
    const column = Math.min(2, Math.floor(point.x * 3));
    const row = Math.min(2, Math.floor(point.y * 3));
    return `${column}:${row}`;
  }));

  for (const cell of coverage.occupied_grid_cells || []) {
    const column = Number(cell?.[0]);
    const row = Number(cell?.[1]);
    if (
      Number.isInteger(column)
      && Number.isInteger(row)
      && column >= 0
      && column <= 2
      && row >= 0
      && row <= 2
    ) {
      occupiedKeys.add(`${column}:${row}`);
    }
  }

  const cells = INTRINSIC_COVERAGE_CELLS.map((cell) => ({
    ...cell,
    covered: occupiedKeys.has(`${cell.column}:${cell.row}`),
  }));
  const missingCells = cells
    .filter((cell) => !cell.covered)
    .sort((left, right) => Number(right.edge) - Number(left.edge));
  const sampleCount = finiteNumber(
    coverage.accepted_sample_count,
    acceptedSamples.length,
  );
  const requiredSampleCount = finiteNumber(
    coverage.required_sample_count,
    8,
  );
  const requiredGridCellCount = finiteNumber(
    coverage.required_grid_cell_count,
    5,
  );
  const edgeSampleCount = finiteNumber(coverage.edge_sample_count);
  const requiredEdgeSampleCount = finiteNumber(
    coverage.required_edge_sample_count,
    2,
  );
  const scaleSpan = finiteNumber(coverage.scale_span);
  const requiredScaleSpan = finiteNumber(
    coverage.required_scale_span,
    0.08,
  );
  const poseDiversity = finiteNumber(coverage.pose_diversity);
  const requiredPoseDiversity = finiteNumber(
    coverage.required_pose_diversity,
    0.12,
  );
  const additionalPositions = Math.max(
    0,
    requiredGridCellCount - occupiedKeys.size,
  );
  const guidance = [];

  if (additionalPositions > 0) {
    guidance.push(
      `將校正板移到${missingCells
        .slice(0, additionalPositions)
        .map((cell) => cell.label)
        .join("、")}`,
    );
  }
  if (edgeSampleCount < requiredEdgeSampleCount) {
    guidance.push("補拍靠近畫面邊緣的位置");
  }
  if (scaleSpan < requiredScaleSpan) {
    guidance.push("增加一近一遠的尺寸變化");
  }
  if (poseDiversity < requiredPoseDiversity) {
    guidance.push("增加校正板傾斜與旋轉角度");
  }
  if (sampleCount < requiredSampleCount) {
    guidance.push(`再取得 ${requiredSampleCount - sampleCount} 張有效樣本`);
  }

  return {
    cells,
    points,
    ready: Boolean(coverage.ready),
    guidance,
    sampleCount,
    requiredSampleCount,
    occupiedCellCount: occupiedKeys.size,
    coverageRate: Math.round(
      (occupiedKeys.size / INTRINSIC_COVERAGE_CELLS.length) * 100,
    ),
    requiredGridCellCount,
    edgeSampleCount,
    requiredEdgeSampleCount,
    scaleReady: scaleSpan >= requiredScaleSpan,
    poseReady: poseDiversity >= requiredPoseDiversity,
  };
}

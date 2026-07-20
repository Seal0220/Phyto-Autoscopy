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

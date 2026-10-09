export function needsStereoPoseReview(run) {
  return ["needs_review", "reviewing", "failed"].includes(run?.status)
    && ["waiting_for_stereo_review", "estimating_stereo_pose", "waiting_for_model_review", "aligning_model_cameras"].includes(run?.stage);
}

export function stereoImagePoint(
  clientX,
  clientY,
  bounds,
  width,
  height,
) {
  if (!bounds.width || !bounds.height || !width || !height) return null;
  const scale = Math.min(bounds.width / width, bounds.height / height);
  const x = (clientX - bounds.left - (bounds.width - width * scale) / 2) / scale;
  const y = (clientY - bounds.top - (bounds.height - height * scale) / 2) / scale;
  if (x < 0 || y < 0 || x >= width || y >= height) return null;
  return { x_px: x, y_px: y };
}

export function completedStereoPairs(
  pairs,
  modelReference = false,
) {
  return pairs.filter((pair) => pair.top && pair.side && (!modelReference || Number.isInteger(pair.model_point_id)));
}

export function stereoValidationCount(validation) {
  if (!["epipolar", "geometric", "reprojection"].includes(validation?.validated_stage)
    || !Array.isArray(validation.inlier_indices)) return null;
  return validation.inlier_indices.length;
}

export function stereoPairCheck(
  validation,
  index,
  camera = null,
) {
  const check = validation?.cameras?.[camera];
  if (check) {
    if ((!check.status || check.status === "accepted") && Array.isArray(check.inlier_indices)) {
      return check.inlier_indices.includes(index) ? "inlier" : "check";
    }
    // A rejected pose's consistent candidates are not verified inliers.
    if (check.status === "rejected" && Array.isArray(check.outlier_indices)) {
      return check.outlier_indices.includes(index) ? "check" : null;
    }
    return null;
  }
  if (stereoValidationCount(validation) === null) return null;
  return validation.inlier_indices.includes(index) ? "inlier" : "check";
}

export function stereoPairLabel(
  pair,
  index,
  validation,
  camera = null,
) {
  const check = stereoPairCheck(validation, index, camera);
  const status = !pair.top || !pair.side ? "待標記"
    : check === "check" ? "需檢查" : check === "inlier" ? "內點" : "已標記";
  return `第 ${index + 1} 組（${status}）`;
}

export function stereoReviewRequest(
  views,
  pairs,
  reference = null,
) {
  const top = views.find((view) => view.camera_id === "top");
  const side = views.find((view) => view.camera_id === "side");
  return {
    top_view_id: top?.view_id,
    side_view_id: side?.view_id,
    correspondences: completedStereoPairs(pairs, Boolean(reference)),
    ...(reference ? { reference_signature: reference.signature } : {}),
  };
}

export function stereoPairsWithModelPoint(
  pairs,
  selected,
  pointId,
) {
  const existing = pairs.findIndex((pair) => pair.model_point_id === pointId);
  if (existing >= 0) return { pairs, selected: existing };
  const empty = !Number.isInteger(pairs[selected]?.model_point_id) ? selected
    : pairs.findIndex((pair) => !Number.isInteger(pair.model_point_id) && !pair.top && !pair.side);
  if (empty >= 0) {
    return {
      pairs: pairs.map((pair, index) => index === empty ? { ...pair, model_point_id: pointId } : pair),
      selected: empty,
    };
  }
  if (pairs.length >= 200) return null;
  return { pairs: [...pairs, { model_point_id: pointId, top: null, side: null }], selected: pairs.length };
}

export function stereoPairsAfterRefresh(
  pairs,
  previous,
  next,
) {
  const sameViews = previous.views.length === next.views.length
    && previous.views.every((view) => next.views.some((candidate) => candidate.view_id === view.view_id));
  if (!sameViews) return next.draft?.correspondences?.length ? next.draft.correspondences : [{ top: null, side: null }];
  if (previous.reference?.signature === next.reference?.signature) return pairs;
  if (next.draft?.correspondences?.length) return next.draft.correspondences;
  // Keep valid image marks, but never reinterpret an old Gaussian ID as a new model vertex.
  return pairs.map(({ top, side }) => ({ top, side }));
}

export function stereoPairsWithMovedModelPoint(
  pairs,
  pointId,
  nextPointId,
) {
  const index = pairs.findIndex((pair) => pair.model_point_id === pointId);
  if (index < 0 || !Number.isInteger(nextPointId)
    || pairs.some((pair, number) => number !== index && pair.model_point_id === nextPointId)) return null;
  return {
    pairs: pairs.map((pair, number) => number === index ? { ...pair, model_point_id: nextPointId } : pair),
    selected: index,
  };
}

export function stereoPairsWithoutPair(
  pairs,
  selected,
  index,
) {
  if (!Number.isInteger(index) || index < 0 || index >= pairs.length) return { pairs, selected };
  const remaining = pairs.filter((_, number) => number !== index);
  return {
    pairs: remaining.length ? remaining : [{ top: null, side: null }],
    selected: Math.max(0, selected > index ? selected - 1 : Math.min(selected, remaining.length - 1)),
  };
}

export function needsStereoPoseReview(run) {
  return ["needs_review", "reviewing", "failed"].includes(run?.status)
    && ["waiting_for_stereo_review", "estimating_stereo_pose"].includes(run?.stage);
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

export function completedStereoPairs(pairs) {
  return pairs.filter((pair) => pair.top && pair.side);
}

export function stereoReviewRequest(
  views,
  pairs,
) {
  const top = views.find((view) => view.camera_id === "top");
  const side = views.find((view) => view.camera_id === "side");
  return {
    top_view_id: top?.view_id,
    side_view_id: side?.view_id,
    correspondences: completedStereoPairs(pairs),
  };
}

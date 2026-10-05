export function gaussianPointIndex(
  reference,
  pointId,
) {
  if (!Number.isInteger(pointId) || !Number.isInteger(reference.gaussian_point_offset)) return null;
  const index = pointId - reference.gaussian_point_offset;
  return index >= 0 && index < reference.gaussian_count ? index : null;
}

export function knownModelPoint(
  reference,
  pointId,
) {
  return Number.isInteger(pointId) && (
    gaussianPointIndex(reference, pointId) !== null
    || reference.points.some((point) => point.id === pointId)
  );
}


export function landmarkInModelSpace(
  landmark,
  reference,
) {
  if (!reference?.model_quality?.immutable_reference) return landmark;
  const transform = reference.model_to_world;
  const xyz = [landmark?.x_mm, landmark?.y_mm, landmark?.z_mm];
  if (!transform || !xyz.every(Number.isFinite)) return null;
  const { scale, rotation, translation } = transform;
  if (!Number.isFinite(scale) || scale <= 0
    || !Array.isArray(rotation) || rotation.length !== 3
    || rotation.some((row) => !Array.isArray(row) || row.length !== 3 || !row.every(Number.isFinite))
    || !Array.isArray(translation) || translation.length !== 3 || !translation.every(Number.isFinite)) return null;
  const centered = xyz.map((value, index) => (value - translation[index]) / scale);
  const modelPoint = [0, 1, 2].map((column) => rotation.reduce(
    (sum, row, index) => sum + row[column] * centered[index],
    0,
  ));
  return { ...landmark, x_mm: modelPoint[0], y_mm: modelPoint[1], z_mm: modelPoint[2] };
}

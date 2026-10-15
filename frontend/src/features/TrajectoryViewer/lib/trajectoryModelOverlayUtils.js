export function trajectoryModelTransform(reference) {
  const transform = reference?.model_to_world;
  if (!transform) {
    const quality = reference?.model_quality;
    if (quality?.immutable_reference || quality?.coordinate_unit !== "millimetre" && quality?.coordinate_space !== "metric_world_mm") return null;
    return { scale: 1, rotation: [[1, 0, 0], [0, 1, 0], [0, 0, 1]], translation: [0, 0, 0] };
  }
  const { scale, rotation, translation } = transform;
  if (!Number.isFinite(scale) || scale <= 0
    || !Array.isArray(rotation) || rotation.length !== 3
    || rotation.some((row) => !Array.isArray(row) || row.length !== 3 || !row.every(Number.isFinite))
    || !Array.isArray(translation) || translation.length !== 3 || !translation.every(Number.isFinite)) return null;
  // A similarity registration must preserve axes and orientation; reject a
  // reflected or malformed matrix instead of distorting the reference model.
  for (let i = 0; i < 3; i += 1) {
    for (let j = 0; j < 3; j += 1) {
      const dot = rotation[i].reduce((sum, value, k) => sum + value * rotation[j][k], 0);
      if (Math.abs(dot - (i === j ? 1 : 0)) > 0.001) return null;
    }
  }
  const [a, b, c] = rotation;
  const determinant = a[0] * (b[1] * c[2] - b[2] * c[1])
    - a[1] * (b[0] * c[2] - b[2] * c[0]) + a[2] * (b[0] * c[1] - b[1] * c[0]);
  return Math.abs(determinant - 1) <= 0.001 ? transform : null;
}

export function trajectoryModelWorldMatrix(transform) {
  const { scale, rotation: r, translation: t } = transform;
  return [
    r[0][0] * scale, r[1][0] * scale, r[2][0] * scale, 0,
    r[0][1] * scale, r[1][1] * scale, r[2][1] * scale, 0,
    r[0][2] * scale, r[1][2] * scale, r[2][2] * scale, 0,
    ...t, 1,
  ];
}

export function trajectoryOverlayCamera(plotElement) {
  const scene = plotElement?._fullLayout?.scene?._scene;
  const gl = scene?.glplot;
  const params = gl?.cameraParams;
  const matrices = [params?.view, params?.projection, params?.model];
  if (!gl?.canvas || !matrices.every((matrix) => matrix?.length === 16 && Array.from(matrix).every(Number.isFinite))
    || scene.dataScale?.length !== 3 || !scene.dataScale.every(Number.isFinite)) return null;
  // Plotly first scales raw data, then applies its native model matrix. Use
  // those exact transforms and the rendered projection, including pan/zoom.
  const world = Array.from(params.model);
  for (let column = 0; column < 3; column += 1) {
    for (let row = 0; row < 4; row += 1) world[column * 4 + row] *= scene.dataScale[column];
  }
  return {
    canvas: gl.canvas,
    view: Array.from(params.view),
    projection: Array.from(params.projection),
    world,
    orthographic: Boolean(params._ortho),
  };
}

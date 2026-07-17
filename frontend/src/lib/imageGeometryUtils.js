export function epipolarSegment(
  coefficients,
  width,
  height,
) {
  if (
    !Array.isArray(coefficients)
    || coefficients.length < 3
    || !Number.isFinite(width)
    || !Number.isFinite(height)
    || width <= 0
    || height <= 0
  ) {
    return null;
  }
  const [a, b, c] = coefficients.map(Number);
  if (![a, b, c].every(Number.isFinite)) return null;
  const candidates = [];

  if (Math.abs(b) > 1e-12) {
    for (const x of [0, width]) {
      const y = -(a * x + c) / b;
      if (y >= 0 && y <= height) candidates.push({ x, y });
    }
  }
  if (Math.abs(a) > 1e-12) {
    for (const y of [0, height]) {
      const x = -(b * y + c) / a;
      if (x >= 0 && x <= width) candidates.push({ x, y });
    }
  }

  const unique = candidates.filter((
    point,
    index,
  ) => (
    candidates.findIndex((candidate) => (
      Math.abs(candidate.x - point.x) < 1e-6
      && Math.abs(candidate.y - point.y) < 1e-6
    )) === index
  ));

  return unique.length >= 2 ? [unique[0], unique[1]] : null;
}

export function pointInsideImage(
  point,
  width,
  height,
) {
  return Boolean(
    point
    && Number.isFinite(point.x)
    && Number.isFinite(point.y)
    && point.x >= 0
    && point.y >= 0
    && point.x < width
    && point.y < height,
  );
}

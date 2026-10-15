function finiteNumber(value) {
  if (value === null || value === undefined || value === "") return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

export function trajectoryMetricSeries(
  trajectory,
  metric,
) {
  const available = (trajectory || []).filter((point) => point.valid && finiteNumber(point[metric.key]) !== null);
  // Do not mix a round index with seconds on the same axis. Legacy data without
  // complete timing uses round order, explicitly labelled as such.
  const hasTime = available.length > 0 && available.every((point) => {
    const seconds = finiteNumber(point.elapsed_seconds);
    return seconds !== null && seconds >= 0;
  });
  const series = [];
  const modes = [...new Set((trajectory || []).map((point) => point.mode_id).filter(Boolean))];
  for (const modeId of modes) {
    const ordered = trajectory.filter((point) => point.mode_id === modeId)
      .sort((left, right) => left.point_index - right.point_index);
    let segment = [];
    for (const point of ordered) {
      const raw = finiteNumber(point[metric.key]);
      const x = finiteNumber(hasTime ? point.elapsed_seconds : point.point_index);
      if (!point.valid || raw === null || x === null) {
        if (segment.length) series.push({ modeId, points: segment });
        segment = [];
        continue;
      }
      if (point.missing_segment && segment.length) {
        series.push({ modeId, points: segment });
        segment = [];
      }
      segment.push({ ...point, chartX: x, chartY: raw * (metric.scale ?? 1) });
    }
    if (segment.length) series.push({ modeId, points: segment });
  }
  return { series, hasTime };
}

export function trajectoryMetricBounds(values) {
  const minimum = Math.min(...values), maximum = Math.max(...values);
  const padding = minimum === maximum ? Math.max(Math.abs(minimum) * .05, 1) : (maximum - minimum) * .08;
  return { minimum: minimum - padding, maximum: maximum + padding, span: maximum - minimum + padding * 2 };
}

export function trajectoryMetricTimeBounds(
  values,
  hasTime,
) {
  const bounds = trajectoryMetricBounds(values);
  if (!hasTime) return bounds;
  const minimum = Math.max(0, bounds.minimum);
  return { ...bounds, minimum, span: bounds.maximum - minimum };
}

export function trajectoryMetricTicks(width) {
  const intervals = Math.min(4, Math.max(1, Math.floor(width / 140)));
  return Array.from({ length: intervals + 1 }, (_, index) => index / intervals);
}

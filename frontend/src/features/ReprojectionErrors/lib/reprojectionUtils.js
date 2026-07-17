export const HIGH_REPROJECTION_ERROR_PX = 10;

function finiteNumber(value) {
  if (value === null || value === undefined || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

export function normalizeReprojectionErrors(payload) {
  return (Array.isArray(payload) ? payload : []).map((item) => ({
    frameId: finiteNumber(item?.frame_id),
    top: finiteNumber(item?.top_error_px),
    side: finiteNumber(item?.side_error_px),
    rotating: finiteNumber(item?.rotating_error_px),
    overall: finiteNumber(item?.overall_error_px),
    refinedOverall: finiteNumber(item?.refined_overall_error_px),
    high: Boolean(item?.high_error),
  })).filter((item) => (
    item.frameId !== null
    && Number.isInteger(item.frameId)
    && item.frameId > 0
    && item.top !== null
    && item.top >= 0
    && item.side !== null
    && item.side >= 0
    && item.overall !== null
    && item.overall >= 0
  )).sort((
    left,
    right,
  ) => left.frameId - right.frameId);
}

export function isHighReprojectionError(
  item,
  threshold = HIGH_REPROJECTION_ERROR_PX,
) {
  return Number.isFinite(item?.top)
    && Number.isFinite(item?.side)
    && Math.max(item.top, item.side) > threshold;
}

export function reprojectionStatistics(errors) {
  const topValues = errors.map((item) => item.top);
  const sideValues = errors.map((item) => item.side);
  const combinedValues = [...topValues, ...sideValues];
  const mean = (items) => items.length
    ? items.reduce((
      sum,
      value,
    ) => sum + value, 0) / items.length
    : 0;
  const overallMean = mean(combinedValues);
  const variance = combinedValues.length
    ? combinedValues.reduce((
      sum,
      value,
    ) => sum + (value - overallMean) ** 2, 0) / combinedValues.length
    : 0;
  const highCount = errors.filter((item) => (
    isHighReprojectionError(item)
  )).length;

  return {
    topMean: mean(topValues),
    sideMean: mean(sideValues),
    overallMean,
    standardDeviation: Math.sqrt(variance),
    maximum: combinedValues.length ? Math.max(...combinedValues) : 0,
    highCount,
    highRatio: errors.length ? highCount / errors.length : 0,
  };
}

export function reprojectionChartPoints(
  errors,
  key,
  {
    width = 760,
    height = 340,
    padding = 34,
    maximum,
  } = {},
) {
  if (errors.length === 0) return [];
  const frames = errors.map((item) => item.frameId);
  const minimumFrame = Math.min(...frames);
  const maximumFrame = Math.max(...frames);
  const frameSpan = Math.max(maximumFrame - minimumFrame, 1);
  const valueMaximum = Math.max(
    maximum || 0,
    ...errors.map((item) => item[key]).filter(Number.isFinite),
    10,
  );

  return errors.filter((item) => Number.isFinite(item[key])).map((item) => ({
    ...item,
    plotX: padding + (
      (item.frameId - minimumFrame) / frameSpan
    ) * (width - padding * 2),
    plotY: height - padding - (
      item[key] / valueMaximum
    ) * (height - padding * 2),
    maximum: valueMaximum,
  }));
}

export function reprojectionHistogram(
  errors,
  binCount = 8,
) {
  if (errors.length === 0) return [];
  const maximum = Math.max(...errors.map((item) => item.overall), 1);
  const binWidth = maximum / binCount;
  const bins = Array.from({ length: binCount }, (
    _,
    index,
  ) => ({
    start: index * binWidth,
    end: (index + 1) * binWidth,
    count: 0,
  }));

  for (const error of errors) {
    const index = Math.min(
      binCount - 1,
      Math.floor(error.overall / binWidth),
    );
    bins[index].count += 1;
  }
  return bins;
}

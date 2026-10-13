export function imageTipTrajectorySeries(
  rounds,
  resolved,
  cameraId,
) {
  const series = [];
  const modes = new Map();
  for (const round of rounds) {
    if (!modes.has(round.mode_id)) modes.set(round.mode_id, []);
    modes.get(round.mode_id).push(round);
  }
  for (const [modeId, items] of modes) {
    let points = [];
    for (const round of items) {
      const tip = resolved.get(round.round_key);
      const observation = tip?.image_tip_confirmed
        ? tip.image_observations?.find((item) => (
          (item.camera_id || item.view_id?.split(":").at(-2)) === cameraId
          && [item.x_px, item.y_px].every((value) => (
            typeof value === "number" && Number.isFinite(value)
          ))
        )) : null;
      if (!observation) {
        if (points.length) series.push({ modeId, points });
        points = [];
        continue;
      }
      points.push({
        ...observation,
        roundKey: round.round_key,
        roundId: round.round_id,
        manuallyCorrected: Boolean(tip.manually_corrected),
      });
    }
    if (points.length) series.push({ modeId, points });
  }
  return series;
}

export function imageTipPlotLayout(series) {
  const points = series.flatMap((item) => item.points);
  if (!points.length) return null;
  const xs = points.map((point) => point.x_px);
  const ys = points.map((point) => point.y_px);
  const centerX = (Math.min(...xs) + Math.max(...xs)) / 2;
  const centerY = (Math.min(...ys) + Math.max(...ys)) / 2;
  const spanX = Math.max(Math.max(...xs) - Math.min(...xs), 2) * 1.16;
  const spanY = Math.max(Math.max(...ys) - Math.min(...ys), 2) * 1.16;
  const scale = Math.min(560 / spanX, 240 / spanY);
  return {
    left: centerX - 280 / scale,
    right: centerX + 280 / scale,
    top: centerY - 120 / scale,
    bottom: centerY + 120 / scale,
    projectX: (value) => 48 + 280 + (value - centerX) * scale,
    projectY: (value) => 16 + 120 + (value - centerY) * scale,
  };
}

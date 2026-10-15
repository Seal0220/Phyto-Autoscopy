import { finiteTrajectoryPoint } from "./trajectoryUtils";

export function trajectoryFrameKey(point) {
  return JSON.stringify([point.mode_id, point.round_id, point.point_index]);
}

export function trajectoryFrames(trajectory) {
  return (trajectory || []).filter((point) => point?.mode_id && finiteTrajectoryPoint(point))
    .map((point, index) => ({ point, key: trajectoryFrameKey(point), index }))
    .sort((left, right) => {
      const a = Date.parse(left.point.timestamp), b = Date.parse(right.point.timestamp);
      if (Number.isFinite(a) && Number.isFinite(b) && a !== b) return a - b;
      return String(left.point.mode_id).localeCompare(String(right.point.mode_id), undefined, { numeric: true })
        || Number(left.point.point_index) - Number(right.point.point_index) || left.index - right.index;
    });
}

export function trajectoryThroughFrame(
  trajectory,
  frames,
  cursor,
) {
  if (cursor === null) return trajectory || [];
  const played = new Set(frames.slice(0, cursor + 1).map((frame) => frame.key));
  // Keep invalid rounds so the plot still breaks lines at missing measurements.
  return (trajectory || []).filter((point) => !finiteTrajectoryPoint(point) || played.has(trajectoryFrameKey(point)));
}

export function trajectoryRoundModels(
  models,
  rounds,
) {
  const byKey = new Map((rounds || []).map((round) => [round.round_key, round]));
  return (models || []).filter((model) => model.status === "completed" && (model.model_path || model.plant_model_path))
    .map((model) => {
      const round = byKey.get(model.round_key);
      return { ...model, mode_id: round?.mode_id, round_id: round?.round_id };
    });
}

export function trajectoryModelVersion(model) {
  return JSON.stringify([
    model.round_key, model.model_id, model.model_path, model.plant_model_path,
    model.training_iterations, model.training_duration_seconds, model.gaussian_count,
    model.model_quality?.reference_geometry_signature, model.model_quality?.model_repaired,
  ]);
}

export function modelsForTrajectoryFrame(
  models,
  frame,
) {
  if (!frame) return models;
  return models.filter((model) => model.mode_id === frame.point.mode_id && model.round_id === frame.point.round_id);
}

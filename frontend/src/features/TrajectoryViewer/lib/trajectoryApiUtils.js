import {
  loadRunCalibration,
  requestAnalysisResource,
} from "@/features/AnalysisRun/lib/analysisRunApiUtils";

export async function loadTrajectoryResults(
  analysisId,
  signal,
) {
  const encodedId = encodeURIComponent(analysisId);
  const run = await requestAnalysisResource(
    `/api/analysis/${encodedId}`,
    {
      signal,
    },
  );
  const calibrationPromise = run?.calibration_id
    ? loadRunCalibration(run.calibration_id, signal)
    : Promise.resolve(null);
  const [trajectory, errors, summary, calibration] = await Promise.all([
    requestAnalysisResource(`/api/analysis/${encodedId}/trajectory`, {
      signal,
      timeoutMs: 60_000,
    }),
    requestAnalysisResource(`/api/analysis/${encodedId}/reprojection-errors`, {
      signal,
      timeoutMs: 60_000,
    }),
    requestAnalysisResource(`/api/analysis/${encodedId}/detection-summary`, {
      signal,
      timeoutMs: 60_000,
    }),
    calibrationPromise,
  ]);
  const frameIds = (Array.isArray(trajectory) ? trajectory : [])
    .map((item) => Number(item?.frame_id))
    .filter((frameId) => Number.isInteger(frameId) && frameId > 0);
  const lastFrameId = frameIds.length > 0 ? Math.max(...frameIds) : null;
  const frame = lastFrameId === null
    ? null
    : await requestAnalysisResource(
      `/api/analysis/${encodedId}/frames/${encodeURIComponent(lastFrameId)}`,
      {
        signal,
      },
    );

  return {
    run,
    trajectory,
    errors,
    summary,
    calibration,
    frame,
  };
}

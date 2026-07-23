import {
  downloadAnalysisExport,
  requestAnalysisResource,
} from "@/features/AnalysisRun/lib/analysisRunApiUtils";

function analysisPath(
  analysisId,
  suffix = "",
) {
  return `/api/analysis/${encodeURIComponent(analysisId)}${suffix}`;
}

export async function loadFormalTrajectoryResults(
  analysisId,
  signal,
) {
  const payload = await Promise.all([
    requestAnalysisResource(analysisPath(analysisId), {
      signal,
    }),
    requestAnalysisResource(analysisPath(analysisId, "/rounds"), {
      signal,
    }),
    requestAnalysisResource(analysisPath(analysisId, "/round-models"), {
      signal,
    }),
    requestAnalysisResource(analysisPath(analysisId, "/tip-landmarks"), {
      signal,
    }),
    requestAnalysisResource(analysisPath(analysisId, "/tip-corrections"), {
      signal,
    }),
    requestAnalysisResource(analysisPath(analysisId, "/tip-trajectory"), {
      signal,
    }),
    requestAnalysisResource(analysisPath(
      analysisId,
      "/tip-trajectory-quality",
    ), {
      signal,
    }),
  ]);

  return {
    run: payload[0],
    rounds: Array.isArray(payload[1]) ? payload[1] : [],
    models: Array.isArray(payload[2]) ? payload[2] : [],
    landmarks: Array.isArray(payload[3]) ? payload[3] : [],
    corrections: Array.isArray(payload[4]) ? payload[4] : [],
    trajectory: Array.isArray(payload[5]) ? payload[5] : [],
    quality: payload[6] && typeof payload[6] === "object"
      ? payload[6]
      : {},
  };
}

export function downloadFormalTrajectoryExport(
  analysisId,
  signal,
) {
  return downloadAnalysisExport(analysisId, signal);
}

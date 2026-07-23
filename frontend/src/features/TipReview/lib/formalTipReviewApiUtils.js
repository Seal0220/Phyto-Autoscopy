import { requestAnalysisResource } from "@/features/AnalysisRun/lib/analysisRunApiUtils";

function analysisPath(
  analysisId,
  suffix = "",
) {
  return `/api/analysis/${encodeURIComponent(analysisId)}${suffix}`;
}

export async function loadFormalTipReview(
  analysisId,
  signal,
) {
  const resources = await Promise.all([
    requestAnalysisResource(analysisPath(analysisId), {
      signal,
    }),
    requestAnalysisResource(analysisPath(analysisId, "/rounds"), {
      signal,
    }),
    requestAnalysisResource(analysisPath(analysisId, "/views"), {
      signal,
    }),
    requestAnalysisResource(analysisPath(analysisId, "/round-models"), {
      signal,
    }),
    requestAnalysisResource(analysisPath(analysisId, "/tip-landmarks"), {
      signal,
    }),
    requestAnalysisResource(analysisPath(analysisId, "/tip-observations"), {
      signal,
    }),
    requestAnalysisResource(analysisPath(analysisId, "/tip-corrections"), {
      signal,
    }),
    requestAnalysisResource(analysisPath(analysisId, "/tip-trajectory"), {
      signal,
    }),
  ]);

  return {
    run: resources[0],
    rounds: Array.isArray(resources[1]) ? resources[1] : [],
    views: Array.isArray(resources[2]) ? resources[2] : [],
    models: Array.isArray(resources[3]) ? resources[3] : [],
    landmarks: Array.isArray(resources[4]) ? resources[4] : [],
    observations: Array.isArray(resources[5]) ? resources[5] : [],
    corrections: Array.isArray(resources[6]) ? resources[6] : [],
    trajectory: Array.isArray(resources[7]) ? resources[7] : [],
  };
}

export function saveFormalTipCorrection(
  analysisId,
  payload,
  signal,
) {
  return requestAnalysisResource(
    analysisPath(analysisId, "/tip-corrections"),
    {
      body: payload,
      method: "POST",
      signal,
      timeoutMs: 30_000,
    },
  );
}

export function deleteFormalTipCorrection(
  analysisId,
  correctionId,
  signal,
) {
  return requestAnalysisResource(
    analysisPath(
      analysisId,
      `/tip-corrections/${encodeURIComponent(correctionId)}`,
    ),
    {
      method: "DELETE",
      signal,
      timeoutMs: 30_000,
    },
  );
}

export function completeFormalTipReview(
  analysisId,
  signal,
) {
  return requestAnalysisResource(
    analysisPath(analysisId, "/reconstruct"),
    {
      body: {
        manual_review_completed: true,
      },
      method: "POST",
      signal,
      timeoutMs: 30_000,
    },
  );
}

export function formalViewImageUrl(
  analysisId,
  viewId,
  coordinateSpace = "reprojection",
) {
  const query = new URLSearchParams({
    coordinate_space: coordinateSpace,
  });
  return analysisPath(
    analysisId,
    `/views/${encodeURIComponent(viewId)}/image?${query.toString()}`,
  );
}

export function formalArtifactUrl(
  analysisId,
  artifactPath,
) {
  const encodedPath = String(artifactPath || "")
    .split(/[\\/]+/)
    .map(encodeURIComponent)
    .join("/");
  return analysisPath(analysisId, `/artifacts/${encodedPath}`);
}

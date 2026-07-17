import { requestAnalysisResource } from "@/features/AnalysisRun/lib/analysisRunApiUtils";

const MAX_EAGER_FRAME_DETAILS = 120;

export function loadTipReviewIndex(
  analysisId,
  signal,
) {
  const encodedId = encodeURIComponent(analysisId);

  return Promise.all([
    requestAnalysisResource(`/api/analysis/${encodedId}`, {
      signal,
    }),
    requestAnalysisResource(`/api/analysis/${encodedId}/frame-pairs`, {
      signal,
    }),
    requestAnalysisResource(`/api/analysis/${encodedId}/corrections`, {
      signal,
    }),
  ]).then(async ([
    run,
    pairs,
    corrections,
  ]) => {
    const frames = Array.isArray(pairs) && pairs.length <= MAX_EAGER_FRAME_DETAILS
      ? await requestAnalysisResource(`/api/analysis/${encodedId}/frames`, {
        signal,
        timeoutMs: 60_000,
      })
      : null;

    return [run, pairs, frames, corrections];
  });
}

export function loadTipReviewFrame(
  analysisId,
  frameId,
  signal,
) {
  return requestAnalysisResource(
    `/api/analysis/${encodeURIComponent(analysisId)}/frames/${encodeURIComponent(frameId)}`,
    {
      signal,
    },
  );
}

export function loadTipReviewCorrections(
  analysisId,
  signal,
) {
  return requestAnalysisResource(
    `/api/analysis/${encodeURIComponent(analysisId)}/corrections`,
    {
      signal,
    },
  );
}

export function saveTipCorrection(
  analysisId,
  payload,
  signal,
) {
  return requestAnalysisResource(
    `/api/analysis/${encodeURIComponent(analysisId)}/corrections`,
    {
      body: payload,
      method: "POST",
      signal,
      timeoutMs: 30_000,
    },
  );
}

export function deleteTipCorrection(
  analysisId,
  correctionId,
  signal,
) {
  return requestAnalysisResource(
    `/api/analysis/${encodeURIComponent(analysisId)}/corrections/${encodeURIComponent(correctionId)}`,
    {
      method: "DELETE",
      signal,
      timeoutMs: 30_000,
    },
  );
}

import { requestAnalysisResource } from "./analysisRunApiUtils";

export function saveAnalysisRoundTip(
  analysisId,
  payload,
  signal,
) {
  return requestAnalysisResource(
    `/api/analysis/${encodeURIComponent(analysisId)}/tip-corrections`,
    {
      body: payload,
      method: "POST",
      signal,
      timeoutMs: 30_000,
    },
  );
}

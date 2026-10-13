const PROCESSED_ROUND_STATUSES = new Set([
  "tip_completed", "tip_only", "tip_invalid", "model_completed",
  "model_failed", "alignment_pending", "failed",
]);

export function analysisTipResults(
  rounds = [],
  landmarks = [],
  corrections = [],
) {
  const resolved = new Map(landmarks.map((item) => [item.round_key, item]));
  const latestCorrections = new Map();
  for (const correction of corrections) {
    latestCorrections.set(correction.round_key, correction);
    if (correction.corrected_tip) resolved.set(correction.round_key, correction.corrected_tip);
  }
  const marked = (round) => {
    if (latestCorrections.get(round.round_key)?.invalid) return false;
    const landmark = resolved.get(round.round_key);
    return Boolean(landmark?.valid || landmark?.image_tip_confirmed);
  };
  const pendingRounds = rounds.filter((round) => (
    PROCESSED_ROUND_STATUSES.has(round.status)
    && !latestCorrections.get(round.round_key)?.invalid
    && !marked(round)
  ));
  return {
    resolved,
    pendingRounds,
    markedCount: rounds.filter(marked).length,
    metricCount: rounds.filter((round) => (
      !latestCorrections.get(round.round_key)?.invalid && resolved.get(round.round_key)?.valid
    )).length,
  };
}

export function analysisRoundResultsUrl(
  analysisId,
  roundKey,
  { missingTips = false } = {},
) {
  const query = new URLSearchParams();
  if (roundKey) query.set("round_key", roundKey);
  else if (missingTips) query.set("tip_filter", "missing");
  const suffix = query.size ? `?${query}` : "";
  return `/analysis/${encodeURIComponent(analysisId)}${suffix}#analysis-round-results`;
}

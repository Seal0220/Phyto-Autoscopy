import { needsStereoPoseReview } from "./analysisStereoReviewUtils";

export function analysisAutoRepairAvailability(
  run,
  formalData,
) {
  const models = new Map((formalData?.models || []).map((item) => [item.round_key, item]));
  const landmarks = new Map((formalData?.landmarks || []).map((item) => [item.round_key, item]));
  const corrections = new Map((formalData?.corrections || []).map((item) => [item.round_key, item]));
  const unresolved = (formalData?.rounds || []).some((round) => {
    const model = models.get(round.round_key);
    const correction = corrections.get(round.round_key);
    const landmark = correction?.corrected_tip || landmarks.get(round.round_key);
    const geometryFailed = ["failed", "alignment_pending", "model_failed"].includes(round.status)
      || ["failed", "alignment_pending"].includes(model?.status);
    const tipFailed = !correction?.invalid && (
      correction?.pending_alignment
      || (["tip_invalid", "tip_only"].includes(round.status) && !landmark?.valid)
    );
    return geometryFailed || tipFailed;
  });

  return {
    visible: run?.status === "failed" || needsStereoPoseReview(run) || unresolved,
    disabled: !["failed", "cancelled", "paused", "completed", "partially_completed", "needs_review", "reviewing"].includes(run?.status)
      || run?.stage === "waiting_for_tip_seed",
    disabledReason: run?.stage === "waiting_for_tip_seed"
      ? "請先完成第一輪尖端初始化。"
      : "請先暫停分析並等待保存完成。",
  };
}

import { redirect } from "next/navigation";
import { analysisRoundResultsUrl } from "@/features/AnalysisRun/lib/analysisTipResultsUtils";

export default function TipReview({
  analysisId,
  initialRoundKey,
}) {
  redirect(analysisRoundResultsUrl(analysisId, initialRoundKey, { missingTips: true }));
}

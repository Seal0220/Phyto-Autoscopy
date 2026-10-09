"use client";

import RetryMessage from "@/components/feedback/RetryMessage";
import useAnalysisRunModelPreview from "../hooks/useAnalysisRunModelPreview";
import AnalysisRunModelReference from "./AnalysisRunModelReference";

export default function AnalysisRunRoundTipModel({
  analysisId,
  model,
  landmark,
  tip,
}) {
  const preview = useAnalysisRunModelPreview({
    analysisId,
    model,
  });
  if (preview.error) {
    return (
      <RetryMessage
        message={preview.error}
        onRetry={preview.retry}
        retrying={preview.loading}
      />
    );
  }
  if (!preview.reference) return <p role="status">讀取本輪模型中…</p>;
  const selected = tip.modelSelection?.signature === preview.reference.signature
    ? tip.modelSelection.pointId : null;
  return (
    <AnalysisRunModelReference
      analysisId={analysisId}
      reference={preview.reference}
      landmark={selected == null ? landmark : null}
      selectedPointId={selected}
      pointIds={selected == null ? [] : [selected]}
      disabled={tip.saving || tip.unknown}
      tipPicking
      onPointChange={(pointId) => tip.selectModelPoint(pointId, preview.reference)}
      onPointMove={(_, pointId) => tip.selectModelPoint(pointId, preview.reference)}
      onPointRemove={() => tip.selectModelPoint(null, preview.reference)}
    />
  );
}

"use client";

import RetryMessage from "@/components/feedback/RetryMessage";

import useAnalysisRunModelPreview from "../hooks/useAnalysisRunModelPreview";
import AnalysisRunModelReference from "./AnalysisRunModelReference";

function AnalysisRunModelPreviewContent({
  analysisId,
  model,
  landmark,
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
  if (!preview.reference) {
    return (
      <div
        className="grid min-h-64 place-items-center rounded-xl border border-white/15 bg-black/30 text-sm font-semibold text-neutral-400"
        role="status"
      >
        讀取模型中…
      </div>
    );
  }
  return (
    <AnalysisRunModelReference
      analysisId={analysisId}
      reference={preview.reference}
      landmark={landmark}
      readOnly
    />
  );
}

export default function AnalysisRunModelPreview({
  analysisId,
  model,
  landmark,
}) {
  if (model?.status !== "completed" || !(model.plant_model_path || model.model_path)) {
    return (
      <p className="m-0 rounded-xl border border-dashed border-white/15 bg-black/15 p-5 text-center text-sm font-semibold text-neutral-400">
        此輪尚無可預覽的 3D 模型。
      </p>
    );
  }
  return (
    <AnalysisRunModelPreviewContent
      key={`${analysisId}:${model.round_key}`}
      analysisId={analysisId}
      model={model}
      landmark={landmark}
    />
  );
}

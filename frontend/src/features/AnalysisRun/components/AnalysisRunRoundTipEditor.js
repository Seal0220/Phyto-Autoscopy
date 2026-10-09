"use client";

import ActionRow from "@/components/actions/ActionRow";
import Button from "@/components/buttons/Button";
import RetryMessage from "@/components/feedback/RetryMessage";
import FormalTipReviewRoundImage from "@/features/TipReview/components/FormalTipReviewRoundImage";
import useAnalysisRunTipCorrection from "../hooks/useAnalysisRunTipCorrection";
import AnalysisRunRoundTipModel from "./AnalysisRunRoundTipModel";

export default function AnalysisRunRoundTipEditor({
  analysisId,
  roundKey,
  views,
  model,
  landmark,
  correction,
  onSaved,
  initializing = false,
  features = [],
  activeFeature,
  onActiveFeature,
}) {
  const fixedViews = ["top", "side"].map((camera) => views.find((view) => view.camera_id === camera)).filter(Boolean);
  const tip = useAnalysisRunTipCorrection({
    analysisId,
    roundKey,
    views: fixedViews,
    correction,
    landmark,
    onSaved,
  });
  const modelReady = model?.status === "completed" && (model.model_path || model.plant_model_path);
  return (
    <div className="grid min-w-0 gap-3">
      <p className="m-0 text-sm text-neutral-300">
        {initializing ? "先在俯視與側視標記同一個生長尖端。儲存後確認影像目標可追蹤，即自動繼續後續輪次。"
          : "在俯視與側視標記同一生長尖端，會更新後續追蹤目標。下方模型可輔助觀察本輪位置。"}
      </p>
      <div className="grid min-w-0 gap-3 min-[720px]:grid-cols-2">
        {fixedViews.map((view, index) => (
          <FormalTipReviewRoundImage
            key={view.view_id}
            analysisId={analysisId}
            view={view}
            viewIndex={index}
            point={tip.points[view.view_id] || null}
            initialCoordinateSpace="undistorted"
            disabled={tip.saving || tip.unknown}
            onPointChange={tip.updatePoint}
            onPointRemove={tip.removePoint}
            features={features}
            activeFeature={activeFeature}
            onActiveFeature={onActiveFeature}
          />
        ))}
      </div>
      {modelReady && !initializing ? (
        <AnalysisRunRoundTipModel
          analysisId={analysisId}
          model={model}
          landmark={landmark}
          tip={tip}
        />
      ) : <p role="status">本輪模型尚未完成，可先儲存俯視與側視尖端標記。</p>}
      <ActionRow>
        <Button
          variant="primary"
          disabled={tip.saving || tip.unknown}
          onClick={tip.save}
        >
          {tip.saving ? "確認中…" : initializing ? "確認尖端並開始追蹤" : "儲存尖端"}
        </Button>
        {tip.notice ? <p className="m-0 text-sm text-neutral-300" role="status">{tip.notice}</p> : null}
      </ActionRow>
      {tip.error ? (
        <RetryMessage
          message={tip.error}
          onRetry={tip.refresh}
          retrying={tip.saving}
        />
      ) : null}
    </div>
  );
}

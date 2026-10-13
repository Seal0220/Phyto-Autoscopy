"use client";

import { FiSave } from "react-icons/fi";
import { createPortal } from "react-dom";

import ActionRow from "@/components/actions/ActionRow";
import Button from "@/components/buttons/Button";
import RetryMessage from "@/components/feedback/RetryMessage";
import AnalysisRunRoundTipImage from "./AnalysisRunRoundTipImage";
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
  onFinishEditing,
  initializing = false,
  features = [],
  activeFeature,
  onActiveFeature,
  actionElement,
}) {
  const fixedViews = ["top", "side"].map((camera) => views.find((view) => view.camera_id === camera)).filter(Boolean);
  const modelReady = model?.status === "completed" && Boolean(model.model_path || model.plant_model_path);
  const tip = useAnalysisRunTipCorrection({
    analysisId,
    roundKey,
    views: fixedViews,
    correction,
    landmark,
    onSaved,
    initializing,
    requireModel: modelReady,
  });
  const saveAction = (
    <Button
      variant="primary"
      disabled={tip.saving || tip.unknown}
      onClick={async () => {
        if (await tip.save()) onFinishEditing?.();
      }}
    >
      <FiSave
        className="size-4 shrink-0"
        aria-hidden="true"
      />
      {tip.saving ? "確認中…" : initializing ? "確認尖端並開始追蹤" : "儲存尖端"}
    </Button>
  );
  return (
    <div className="@container grid min-w-0 gap-3">
      <p className="m-0 text-sm text-neutral-300">
        {initializing ? modelReady
          ? "第一輪模型已完成。請在俯視、側視及下方模型標記同一生長尖端；確認追蹤起點後，自動處理後續輪次。"
          : "請在俯視與側視標記同一生長尖端，確認追蹤起點後自動處理後續輪次。"
          : "在俯視與側視標記同一生長尖端，會更新後續追蹤目標。下方模型可輔助觀察本輪位置。"}
      </p>
      <div className="grid min-w-0 gap-3 @min-[720px]:grid-cols-2">
        {fixedViews.map((view, index) => (
          <AnalysisRunRoundTipImage
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
      {modelReady ? (
        <AnalysisRunRoundTipModel
          analysisId={analysisId}
          model={model}
          landmark={landmark}
          tip={tip}
        />
      ) : !initializing ? <p role="status">本輪模型尚未完成，可先儲存俯視與側視尖端標記。</p> : null}
      {actionElement === undefined ? (
        <ActionRow>
          {saveAction}
          {tip.notice ? <p className="m-0 text-sm text-neutral-300" role="status">{tip.notice}</p> : null}
        </ActionRow>
      ) : (
        <>
          {actionElement ? createPortal(saveAction, actionElement) : null}
          {tip.notice ? <p className="m-0 text-sm text-neutral-300" role="status">{tip.notice}</p> : null}
        </>
      )}
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

import InformationGrid from "@/components/data/InformationGrid";
import SubsectionHeader from "@/components/headers/SubsectionHeader";
import InnerPanel from "@/components/panels/InnerPanel";
import { StatusPill } from "@/components/panels/Panel";
import {
  ANALYSIS_MODEL_STATUS_META,
  RECONSTRUCTION_BACKEND_LABELS,
} from "@/features/Analysis/analysisConfig";

import AnalysisRunModelPreview from "@/features/AnalysisRun/components/AnalysisRunModelPreview";

function displayRatio(value) {
  return value == null || !Number.isFinite(Number(value))
    ? "尚無資料"
    : `${(Number(value) * 100).toFixed(1)}%`;
}

export default function FormalTipReviewModel({
  analysisId,
  model,
  landmark,
}) {
  const quality = model?.model_quality || {};
  const status = ANALYSIS_MODEL_STATUS_META[model?.status] || {
    label: "尚無模型",
    tone: "neutral",
  };

  return (
    <InnerPanel>
      <SubsectionHeader
        title="每輪植物模型"
      >
        <StatusPill tone={status.tone}>
          {status.label}
        </StatusPill>
      </SubsectionHeader>
      <AnalysisRunModelPreview
        analysisId={analysisId}
        model={model}
        landmark={landmark}
      />
      <InformationGrid
        items={[
          {
            label: "模型後端",
            value: RECONSTRUCTION_BACKEND_LABELS[model?.backend] || "尚無資料",
          },
          {
            label: "Gaussian 數量",
            value: model?.gaussian_count ?? "尚無資料",
          },
          {
            label: "完整點數",
            value: model?.point_count ?? "尚無資料",
          },
          {
            label: "植物點數比例",
            value: displayRatio(quality.plant_isolation?.retained_ratio),
          },
          {
            label: "骨架節點",
            value: quality.skeleton_node_count ?? "尚無資料",
          },
          {
            label: "骨架端點",
            value: quality.skeleton_endpoint_count ?? "尚無資料",
          },
        ]}
        rows={2}
        minimumColumnWidth
        scroll
      />
    </InnerPanel>
  );
}

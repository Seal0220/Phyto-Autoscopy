import FullscreenImage from "@/components/media/FullscreenImage";
import InformationGrid from "@/components/data/InformationGrid";
import SubsectionHeader from "@/components/headers/SubsectionHeader";
import InnerPanel from "@/components/panels/InnerPanel";
import { StatusPill } from "@/components/panels/Panel";
import {
  ANALYSIS_MODEL_STATUS_META,
  RECONSTRUCTION_BACKEND_LABELS,
} from "@/features/Analysis/analysisConfig";

import { formalArtifactUrl } from "../lib/formalTipReviewApiUtils";

function displayRatio(value) {
  return value == null || !Number.isFinite(Number(value))
    ? "尚無資料"
    : `${(Number(value) * 100).toFixed(1)}%`;
}

export default function FormalTipReviewModel({
  analysisId,
  model,
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
        description="模型預覽、完整場景與純植物輸出均屬於目前輪次。"
      >
        <StatusPill tone={status.tone}>
          {status.label}
        </StatusPill>
      </SubsectionHeader>
      {model?.preview_paths?.length ? (
        <div className="grid gap-3 min-[720px]:grid-cols-2 min-[1200px]:grid-cols-3">
          {model.preview_paths.map((path, index) => {
            const url = formalArtifactUrl(analysisId, path);
            return (
              <div
                className="relative overflow-hidden rounded-xl border border-white/15 bg-black"
                key={path}
              >
                {/* 分析產物由受保護的動態 API 提供。 */}
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  className="block aspect-video w-full object-contain"
                  src={url}
                  alt={`每輪植物模型預覽 ${index + 1}`}
                />
                <FullscreenImage
                  src={url}
                  alt={`每輪植物模型預覽 ${index + 1}`}
                  label={`模型預覽 ${index + 1}`}
                />
              </div>
            );
          })}
        </div>
      ) : (
        <p className="m-0 rounded-xl border border-dashed border-white/15 bg-black/15 p-5 text-center text-sm font-semibold text-neutral-400">
          此輪尚無可顯示的模型預覽。
        </p>
      )}
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

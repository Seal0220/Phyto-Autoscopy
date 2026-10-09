"use client";

import { PiArrowCounterClockwise } from "react-icons/pi";
import Button from "@/components/buttons/Button";
import SubsectionHeader from "@/components/headers/SubsectionHeader";
import RetryMessage from "@/components/feedback/RetryMessage";
import useAnalysisRunModelViewer from "../hooks/useAnalysisRunModelViewer";

export default function AnalysisRunModelReference({
  analysisId,
  reference,
  landmark,
  selectedPointId,
  pointIds,
  pairNumber,
  disabled,
  onPointChange,
  onPointMove,
  onPointRemove,
  readOnly = false,
  tipPicking = false,
}) {
  const model = useAnalysisRunModelViewer({
    analysisId,
    reference,
    landmark,
    selectedPointId,
    pointIds,
    disabled,
    onPointChange: readOnly ? undefined : onPointChange,
    onPointMove,
    onPointRemove,
    tipPicking,
  });
  const locked = disabled || !model.ready;
  const alignmentPoints = reference.model_quality?.representation === "sfm_points";
  const alignmentPreview = reference.model_quality?.representation === "alignment_3dgs";
  const cameraCounts = reference.model_quality?.training_camera_counts;
  const missingFixedViews = cameraCounts && (!cameraCounts.top || !cameraCounts.side);
  return (
    <div className="grid min-w-0 gap-3">
      <SubsectionHeader
        title={tipPicking ? "模型尖端標記" : readOnly ? "參考模型" : alignmentPoints ? "稀疏參照點" : alignmentPreview ? "對齊預覽" : "模型選點"}
        description={tipPicking ? "點選尖端，拖動調整，右鍵刪除標記；拖曳空白處旋轉模型。" : readOnly ? "拖曳旋轉，滾輪縮放。" : reference.model_quality?.immutable_reference
          ? "校正只更新量測位置，參考模型保留。"
          : alignmentPoints
          ? "尚未建模，請按「重建預覽」取得選點模型。"
          : alignmentPreview ? "標記相同位置，通過後建立三鏡頭模型；拖曳旋轉，滾輪縮放。"
          : "拖動標記調整，右鍵刪除；拖曳空白旋轉，滾輪縮放。"}
      >
        <Button
          disabled={locked}
          onClick={model.reset}
        >
          <PiArrowCounterClockwise
            className="size-4 shrink-0"
            aria-hidden="true"
          />
          重設鏡頭
        </Button>
      </SubsectionHeader>
      {missingFixedViews ? (
        <p className="m-0 text-sm font-semibold text-amber-200" role="status">
          參考模型參與訓練：俯視 {cameraCounts.top || 0} 張、側視 {cameraCounts.side || 0} 張、旋臂 {cameraCounts.rotating || 0} 張。缺少的鏡頭未納入此模型；影像尖端標記與追蹤仍可使用，三維毫米位置須另通過量測校正。
        </p>
      ) : null}
      <div className="relative min-w-0 overflow-hidden rounded-xl border border-white/15 bg-black/30">
        <div
          ref={model.element}
          tabIndex={0}
          role="region"
          aria-label={readOnly
            ? "3D模型預覽，拖曳或方向鍵旋轉，右鍵拖曳平移，滾輪縮放，0 重設鏡頭"
            : "3D模型選點，點選新增、拖動標記調整、右鍵點標記刪除；拖曳空白或方向鍵旋轉，右鍵拖曳空白平移，滾輪縮放，0 重設鏡頭"}
          aria-busy={!model.ready && !model.error}
          className={`relative aspect-[4/3] max-h-[560px] min-h-64 w-full focus-visible:outline-2 focus-visible:outline-emerald-300
            ${readOnly ? "cursor-grab active:cursor-grabbing" : "cursor-crosshair"}`}
        />
        {!model.ready && !model.error ? (
          <p
            className="pointer-events-none absolute inset-0 grid place-items-center bg-[#06100c]/90 text-sm text-neutral-300"
            role="status"
          >
            {model.progress < 100 ? `載入模型 ${model.progress}%` : "準備模型…"}
          </p>
        ) : null}
        {model.error ? (
          <div className="absolute inset-0 grid place-items-center bg-[#06100c]/95 p-4">
            <RetryMessage
              message={model.error}
              onRetry={model.retry}
            />
          </div>
        ) : null}
      </div>
      {!readOnly ? (
        <p
          className="text-xs text-neutral-400"
          role="status"
        >
          {model.notice || (tipPicking
            ? Number.isInteger(selectedPointId) ? "已選模型尖端，按儲存即可更新本輪標記。" : "在模型點選尖端，或使用上方俯視與側視標記。"
            : Number.isInteger(selectedPointId) ? `第 ${pairNumber} 組已選參照點，再標記下方兩張影像。` : "請選芽尖、葉尖或莖節等清楚的位置。")}
        </p>
      ) : null}
    </div>
  );
}

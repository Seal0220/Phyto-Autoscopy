"use client";

import { PiArrowCounterClockwise } from "react-icons/pi";
import Button from "@/components/buttons/Button";
import SubsectionHeader from "@/components/headers/SubsectionHeader";
import RetryMessage from "@/components/feedback/RetryMessage";
import useAnalysisRunModelViewer from "../hooks/useAnalysisRunModelViewer";

export default function AnalysisRunModelReference({
  analysisId,
  reference,
  selectedPointId,
  pointIds,
  pairNumber,
  disabled,
  onPointChange,
}) {
  const model = useAnalysisRunModelViewer({
    analysisId,
    reference,
    selectedPointId,
    pointIds,
    disabled,
    onPointChange,
  });
  const locked = disabled || !model.ready;
  return (
    <div className="grid min-w-0 gap-3">
      <SubsectionHeader
        title="模型選點"
        description="點選新增參照點，拖曳旋轉，滾輪縮放。"
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
      <div className="relative min-w-0 overflow-hidden rounded-xl border border-white/15 bg-black/30">
        <div
          ref={model.element}
          tabIndex={0}
          role="region"
          aria-label="3D模型選點，拖曳或方向鍵旋轉，右鍵拖曳或 Shift 加方向鍵平移，滾輪或加減鍵縮放，0 重設鏡頭"
          aria-busy={!model.ready && !model.error}
          className="relative aspect-[4/3] max-h-[560px] min-h-64 w-full cursor-crosshair focus-visible:outline-2 focus-visible:outline-emerald-300"
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
      <p
        className="text-xs text-neutral-400"
        role="status"
      >
        {model.notice || (Number.isInteger(selectedPointId) ? `第 ${pairNumber} 組已選參照點，再標記下方兩張影像。` : "請選芽尖、葉尖或莖節等清楚的位置。")}
      </p>
    </div>
  );
}

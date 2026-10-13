"use client";

import { useMemo } from "react";
import { FiRotateCcw } from "react-icons/fi";

import Button from "@/components/buttons/Button";
import RetryMessage from "@/components/feedback/RetryMessage";
import SubsectionHeader from "@/components/headers/SubsectionHeader";
import InnerPanel from "@/components/panels/InnerPanel";

import { buildFormalTrajectoryPlot, formalTrajectoryRanges } from "../lib/trajectoryUtils";
import useFormalTrajectoryPlot from "../hooks/useFormalTrajectoryPlot";

export default function FormalTrajectoryViewer3D({
  analysisId,
  trajectory,
}) {
  const { traces, validCount } = useMemo(
    () => buildFormalTrajectoryPlot(trajectory || []),
    [trajectory],
  );

  const ranges = useMemo(() => formalTrajectoryRanges(trajectory), [trajectory]);
  const { plotElementRef, loadError, loading, resetCamera, retry } = useFormalTrajectoryPlot({
    analysisId,
    traces,
    ranges,
    hasPoints: validCount > 0,
  });

  return (
    <InnerPanel>
      <SubsectionHeader
        title="三維尖端軌跡"
        description="拖曳旋轉、滾輪縮放；X／Y／Z 同尺度（mm），座標框保留留白，缺失輪次不連線。"
      >
        <Button
          className="min-h-9 px-3 text-xs"
          disabled={!validCount || loading || Boolean(loadError)}
          onClick={resetCamera}
        >
          <FiRotateCcw
            className="size-3.5 shrink-0"
            aria-hidden="true"
          />
          重設視角
        </Button>
      </SubsectionHeader>

      {validCount ? (
        <div className="relative h-[min(65vh,640px)] min-h-80 min-w-0 overflow-hidden rounded-xl border border-white/15 bg-black/30">
          <div
            ref={plotElementRef}
            className="size-full"
            aria-label="可旋轉縮放的三維尖端軌跡科學圖"
          />
          {loading && !loadError ? (
            <p
              className="absolute inset-0 grid place-items-center bg-[#06100c]/75 text-sm font-semibold text-neutral-300"
              role="status"
            >
              載入三維圖表中…
            </p>
          ) : null}
          {loadError ? (
            <div className="absolute inset-0 grid place-items-center bg-[#06100c]/95 p-4">
              <RetryMessage
                message={loadError}
                onRetry={retry}
                retryLabel="重新載入圖表"
              />
            </div>
          ) : null}
        </div>
      ) : (
        <p className="m-0 rounded-xl border border-dashed border-white/15 bg-black/15 p-5 text-center text-sm font-semibold text-neutral-400">
          本次分析沒有可顯示的有效三維尖端標記。
        </p>
      )}

      {validCount ? (
        <p className="m-0 text-xs font-semibold text-neutral-400">
          圖例可切換各模式；白色點為人工修正，空心圓為起點、實心圓為終點、菱形為世界原點。
        </p>
      ) : null}
    </InnerPanel>
  );
}

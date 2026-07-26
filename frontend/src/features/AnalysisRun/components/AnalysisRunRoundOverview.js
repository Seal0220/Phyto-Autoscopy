import InformationGrid from "@/components/data/InformationGrid";
import SubsectionHeader from "@/components/headers/SubsectionHeader";
import InnerPanel from "@/components/panels/InnerPanel";
import { StatusPill } from "@/components/panels/Panel";
import {
  ANALYSIS_MODEL_STATUS_META,
} from "@/features/Analysis/analysisConfig";

import { analysisRoundStatus } from "../lib/analysisRunUtils";

function displayNumber(
  value,
  suffix = "",
  digits = 1,
) {
  const number = Number(value);
  return Number.isFinite(number)
    ? `${number.toFixed(digits)}${suffix}`
    : "尚無資料";
}

export default function AnalysisRunRoundOverview({
  formalData,
}) {
  const rounds = formalData?.rounds || [];
  const modelsByRound = new Map(
    (formalData?.models || []).map((item) => [item.round_key, item]),
  );
  const landmarksByRound = new Map(
    (formalData?.landmarks || []).map((item) => [item.round_key, item]),
  );

  return (
    <InnerPanel>
      <SubsectionHeader
        title="Round 執行結果"
        description="每個模式與 Round 保持獨立，列出模型、尖端標記及品質狀態。"
      >
        <StatusPill tone={rounds.length ? "success" : "neutral"}>
          {rounds.length} 輪
        </StatusPill>
      </SubsectionHeader>

      {rounds.length ? (
        <div className="max-h-[34rem] overflow-auto rounded-xl border border-white/15">
          <div className="grid min-w-[64rem] grid-cols-[1.2fr_0.8fr_0.9fr_0.8fr_0.8fr_0.9fr_0.9fr] gap-3 border-b border-white/15 bg-white/7 px-3 py-2 text-xs font-black text-neutral-300">
            <span>模式</span>
            <span>Round</span>
            <span>狀態</span>
            <span>視角</span>
            <span>旋臂視角</span>
            <span>模型</span>
            <span>尖端標記</span>
          </div>
          {rounds.map((item) => {
            const status = analysisRoundStatus(item.status);
            const model = modelsByRound.get(item.round_key);
            const landmark = landmarksByRound.get(item.round_key);
            const modelStatus = ANALYSIS_MODEL_STATUS_META[
              model?.status
            ] || {
              label: "尚無模型",
              tone: "neutral",
            };

            return (
              <div
                className="grid min-w-[64rem] grid-cols-[1.2fr_0.8fr_0.9fr_0.8fr_0.8fr_0.9fr_0.9fr] items-center gap-3 border-b border-white/10 px-3 py-2 text-xs font-semibold text-neutral-300 last:border-b-0"
                key={item.round_key}
              >
                <span className="truncate font-black text-white">
                  {item.mode_id}
                </span>
                <span>{item.round_id}</span>
                <StatusPill tone={status.tone}>
                  {status.label}
                </StatusPill>
                <span>{item.view_count || 0} 個</span>
                <span>{item.rotating_view_count || 0} 個</span>
                <StatusPill tone={modelStatus.tone}>
                  {modelStatus.label}
                </StatusPill>
                <span>
                  {landmark?.valid
                    ? displayNumber(landmark.confidence * 100, "%", 1)
                    : "不可確認"
                  }
                </span>
              </div>
            );
          })}
        </div>
      ) : (
        <p className="m-0 rounded-xl border border-dashed border-white/15 bg-black/15 p-5 text-center text-sm font-semibold text-neutral-400">
          尚未建立可顯示的 Analysis Round。
        </p>
      )}

      <InformationGrid
        items={[
          {
            label: "總 Round",
            value: `${rounds.length} 輪`,
          },
          {
            label: "完成模型",
            value: `${[...modelsByRound.values()].filter((item) => item.status === "completed").length} 個`,
          },
          {
            label: "有效尖端標記",
            value: `${[...landmarksByRound.values()].filter((item) => item.valid).length} 個`,
          },
          {
            label: "軌跡點",
            value: `${formalData?.trajectory?.length || 0} 點`,
          },
        ]}
        rows={2}
        minimumColumnWidth
        scroll
      />
    </InnerPanel>
  );
}

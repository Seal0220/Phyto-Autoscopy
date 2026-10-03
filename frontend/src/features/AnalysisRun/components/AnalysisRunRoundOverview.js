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
        title="各輪結果"
        description="依模式與輪次查看模型、尖端標記及品質狀態。"
      >
        <StatusPill tone={rounds.length ? "success" : "neutral"}>
          {rounds.length} 輪
        </StatusPill>
      </SubsectionHeader>

      {rounds.length ? (
        <div className="grid max-h-[34rem] gap-2 overflow-y-auto overscroll-contain pr-1">
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
              <article
                className="grid min-w-0 gap-3 rounded-xl border border-white/15 bg-black/15 p-3"
                key={item.round_key}
              >
                <div className="flex min-w-0 flex-wrap items-center gap-2">
                  <h4 className="m-0 min-w-0 break-all text-sm font-black text-white">
                    {item.mode_id} · {item.round_id}
                  </h4>
                  <StatusPill tone={status.tone}>{status.label}</StatusPill>
                  <StatusPill tone={modelStatus.tone}>{modelStatus.label}</StatusPill>
                </div>
                <InformationGrid
                  items={[
                    { label: "影像", value: `${item.view_count || 0} 張` },
                    { label: "旋臂視角", value: `${item.rotating_view_count || 0} 張` },
                    {
                      label: "尖端標記信心",
                      value: landmark?.valid
                        ? displayNumber(landmark.confidence * 100, "%", 1)
                        : "不可確認",
                      tone: landmark?.valid ? "success" : "warning",
                    },
                  ]}
                  border="none"
                  rows={2}
                  stackAtSmall
                />
              </article>
            );
          })}
        </div>
      ) : (
        <p className="m-0 rounded-xl border border-dashed border-white/15 bg-black/15 p-5 text-center text-sm font-semibold text-neutral-400">
          尚無可顯示的分析輪次。
        </p>
      )}

      <InformationGrid
        items={[
          {
            label: "總輪次",
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

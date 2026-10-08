import InformationGrid from "@/components/data/InformationGrid";
import SubsectionHeader from "@/components/headers/SubsectionHeader";
import InnerPanel from "@/components/panels/InnerPanel";
import { StatusPill } from "@/components/panels/Panel";
import AnalysisRunRoundRow from "./AnalysisRunRoundRow";

export default function AnalysisRunRoundOverview({
  analysisId,
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
        <div className="grid min-w-0 gap-2">
          {rounds.map((item) => (
            <AnalysisRunRoundRow
              key={item.round_key}
              analysisId={analysisId}
              round={item}
              model={modelsByRound.get(item.round_key)}
              landmark={landmarksByRound.get(item.round_key)}
            />
          ))}
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

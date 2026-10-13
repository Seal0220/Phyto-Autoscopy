"use client";

import {
  useId,
  useState,
} from "react";

import InformationGrid from "@/components/data/InformationGrid";
import { SelectInput } from "@/components/inputs/Input";
import SubsectionHeader from "@/components/headers/SubsectionHeader";
import InnerPanel from "@/components/panels/InnerPanel";
import { ANALYSIS_MODEL_STATUS_META } from "@/features/Analysis/analysisConfig";
import { analysisRoundStatus } from "../lib/analysisRunUtils";
import { analysisTipResults } from "../lib/analysisTipResultsUtils";
import AnalysisRunRoundDetail from "./AnalysisRunRoundDetail";
import AnalysisRunRoundList from "./AnalysisRunRoundList";

export default function AnalysisRunRoundOverview({
  analysisId,
  formalData,
  initialRoundKey,
  initialTipFilter = "all",
  busy,
  onReloadRun,
}) {
  const [selectedRoundKey, setSelectedRoundKey] = useState(initialRoundKey || null);
  const [tipFilter, setTipFilter] = useState(initialTipFilter);
  const idPrefix = useId();
  const contentId = `${idPrefix}-content`;
  const rounds = formalData?.rounds || [];
  const results = analysisTipResults(rounds, formalData?.landmarks, formalData?.corrections);
  const visibleRounds = tipFilter === "missing" ? results.pendingRounds : rounds;
  const selectedRound = visibleRounds.find((item) => item.round_key === selectedRoundKey)
    || visibleRounds[0];
  const modelsByRound = new Map(
    (formalData?.models || []).map((item) => [item.round_key, item]),
  );
  const landmarksByRound = new Map(
    (formalData?.landmarks || []).map((item) => [item.round_key, item]),
  );
  const correctionsByRound = new Map(
    (formalData?.corrections || []).map((item) => [item.round_key, item]),
  );
  for (const correction of formalData?.corrections || []) {
    if (correction.corrected_tip) landmarksByRound.set(correction.round_key, correction.corrected_tip);
  }

  return (
    <InnerPanel
      id="analysis-round-results"
      className="h-[calc(100dvh-7rem)] min-h-0 min-w-0 scroll-mt-24 grid-rows-[auto_minmax(0,1fr)_auto] max-[980px]:h-[calc(100dvh-9rem)] max-[980px]:scroll-mt-32 max-sm:p-2"
    >
      <SubsectionHeader
        title="各輪結果"
        description="可逐輪補標或修改尖端。"
        className="max-[520px]:grid-cols-1"
      >
        <SelectInput
          id={`${idPrefix}-tip-filter`}
          label="顯示輪次"
          className="w-44 max-[520px]:w-full"
          value={tipFilter}
          onValueChange={setTipFilter}
          options={[
            { value: "all", label: `全部輪次（${rounds.length}）` },
            { value: "missing", label: `尖端待補標（${results.pendingRounds.length}）` },
          ]}
        />
      </SubsectionHeader>

      {selectedRound ? (
        <div className="grid min-h-0 min-w-0 grid-cols-[minmax(0,2fr)_minmax(0,3fr)] gap-2 min-[520px]:grid-cols-[minmax(10rem,1fr)_minmax(0,2fr)] min-[720px]:grid-cols-[minmax(12rem,18rem)_minmax(0,1fr)] min-[720px]:gap-3">
          <AnalysisRunRoundList
            items={visibleRounds.map((item) => {
              const model = modelsByRound.get(item.round_key);
              return {
                roundKey: item.round_key,
                modeId: item.mode_id,
                roundId: item.round_id,
                status: analysisRoundStatus(item.status, {
                  model,
                  landmark: landmarksByRound.get(item.round_key),
                  correction: correctionsByRound.get(item.round_key),
                }),
                modelStatus: item.status === "alignment_pending" && model?.status === "alignment_pending"
                  ? null : ANALYSIS_MODEL_STATUS_META[model?.status] || { label: "尚無模型", tone: "neutral" },
              };
            })}
            selectedRoundKey={selectedRound.round_key}
            idPrefix={idPrefix}
            contentId={contentId}
            onSelect={setSelectedRoundKey}
          />
          <section
            key={selectedRound.round_key}
            id={contentId}
            role="tabpanel"
            aria-labelledby={`${idPrefix}-${encodeURIComponent(selectedRound.round_key)}`}
            className="min-h-0 min-w-0 overflow-hidden rounded-xl border border-white/15 bg-black/15"
          >
            <AnalysisRunRoundDetail
              analysisId={analysisId}
              round={selectedRound}
              model={modelsByRound.get(selectedRound.round_key)}
              landmark={landmarksByRound.get(selectedRound.round_key)}
              correction={correctionsByRound.get(selectedRound.round_key)}
              busy={busy}
              onReloadRun={onReloadRun}
            />
          </section>
        </div>
      ) : (
        <p className="m-0 grid min-h-0 place-items-center rounded-xl border border-dashed border-white/15 bg-black/15 p-5 text-center text-sm font-semibold text-neutral-400">
          {rounds.length ? "目前沒有待補標的尖端；可切換全部輪次查看或修改。" : "尚無可顯示的分析輪次。"}
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
            label: "尖端標記／三維量測",
            value: `${results.markedCount} ／ ${results.metricCount} 個`,
          },
          {
            label: "尖端待補標",
            value: `${results.pendingRounds.length} 輪`,
          },
        ]}
        rows={2}
        minimumColumnWidth
        scroll
      />
    </InnerPanel>
  );
}

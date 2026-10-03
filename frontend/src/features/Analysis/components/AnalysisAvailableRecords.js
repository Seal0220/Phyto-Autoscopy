import {
  FiCheckCircle,
  FiPlusCircle,
} from "react-icons/fi";

import Button from "@/components/buttons/Button";
import InformationGrid from "@/components/data/InformationGrid";
import SubsectionHeader from "@/components/headers/SubsectionHeader";
import { StatusPill } from "@/components/panels/Panel";

import { analysisRecordSummaryItems } from "../lib/analysisUtils";

export default function AnalysisAvailableRecords({
  selectedRecordId,
  sources,
  onSelect,
}) {
  const availableSources = sources.filter((source) => source.ready);

  return (
    <section
      className="grid gap-3"
      aria-labelledby="analysis-record-selection-title"
    >
      <SubsectionHeader
        titleId="analysis-record-selection-title"
        title="選擇紀錄"
        description="選一筆捕捉紀錄；選取後會掃描影像，再選擇模式及分析視角。"
      />

      <div
        className="max-h-[32rem] min-h-0 overflow-y-auto overscroll-contain rounded-xl border border-white/15 bg-black/15 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-300"
        aria-label="紀錄選擇清單"
        role="list"
        tabIndex={0}
      >
        {availableSources.length ? availableSources.map((source) => {
          const selected = source.record_id === selectedRecordId;
          const metrics = analysisRecordSummaryItems(source);

          return (
            <article
              className={`grid min-w-0 grid-cols-1 items-center gap-3 border-b border-white/15 p-4 last:border-b-0 min-[720px]:grid-cols-[minmax(0,1fr)_8.5rem] ${selected ? "bg-emerald-500/10" : "hover:bg-white/[0.04]"}`}
              key={source.record_id}
              role="listitem"
            >
              <div className="grid min-w-0 gap-3">
                <div className="flex min-w-0 flex-wrap items-center justify-between gap-2">
                  <h3 className="m-0 min-w-0 break-all text-sm font-black tracking-widest text-white">
                    {source.record_id || "未命名紀錄"}
                  </h3>

                  <StatusPill tone="success">
                    {selected ? "已選擇" : "可選擇"}
                  </StatusPill>
                </div>

                <InformationGrid
                  items={metrics.map((item) => ({
                    ...item,
                    truncate: true,
                  }))}
                  rows={2}
                  stackAtSmall
                />
              </div>

              <Button
                className="w-full justify-center"
                variant={selected ? "default" : "primary"}
                disabled={selected}
                onClick={() => void onSelect(source.record_id)}
              >
                {selected ? (
                  <FiCheckCircle
                    className="size-4 shrink-0"
                    aria-hidden="true"
                  />
                ) : (
                  <FiPlusCircle
                    className="size-4 shrink-0"
                    aria-hidden="true"
                  />
                )}
                {selected ? "已選擇" : "選擇"}
              </Button>
            </article>
          );
        }) : (
          <p
            className="m-0 p-4 text-center text-sm font-semibold text-neutral-400"
            role="listitem"
          >
            尚無可供分析的紀錄。
          </p>
        )}
      </div>
    </section>
  );
}

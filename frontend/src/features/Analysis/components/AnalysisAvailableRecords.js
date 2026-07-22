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
        description="選擇紀錄後會自動帶入紀錄根目錄、擷取模式並完成掃描。"
      />

      <div
        className="max-h-80 min-h-0 overflow-y-auto overscroll-contain rounded-xl border border-white/15 bg-white/4 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-300"
        aria-label="紀錄選擇清單"
        role="list"
        tabIndex={0}
      >
        {availableSources.length ? availableSources.map((source) => {
          const selected = source.record_id === selectedRecordId;
          const metrics = analysisRecordSummaryItems(source);

          return (
            <article
              className="grid min-w-0 grid-cols-[minmax(0,1fr)_8.5rem] items-center gap-3 border-b border-white/15 p-4 last:border-b-0 max-[720px]:grid-cols-1"
              key={source.record_id}
              role="listitem"
            >
              <div className="grid min-w-0 gap-3">
                <div className="flex min-w-0 flex-wrap items-center justify-between gap-2">
                  <h3 className="m-0 min-w-0 break-all text-sm font-black tracking-widest text-white">
                    {source.record_id || "未命名紀錄"}
                  </h3>

                  <div className="flex flex-row gap-2">
                    <StatusPill tone="success">可分析</StatusPill>
                    {selected ? (
                      <StatusPill tone="success">已選擇</StatusPill>
                    ) : null}
                  </div>
                </div>

                <InformationGrid
                  items={metrics}
                  rows={1}
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

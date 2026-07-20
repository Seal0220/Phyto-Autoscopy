import {
  FiCheckCircle,
  FiEdit3,
  FiPlusCircle,
} from "react-icons/fi";

import Button from "@/components/buttons/Button";
import SubsectionHeader from "@/components/headers/SubsectionHeader";
import { StatusPill } from "@/components/panels/Panel";
import { formatDateTime } from "@/lib/formatUtils";

export default function AnalysisAvailableRecords({
  selectedRecordId,
  sources,
  onSelect,
}) {
  const availableSources = sources.filter((source) => source.ready);

  return (
    <section
      className="grid gap-3"
      aria-labelledby="analysis-available-records-title"
    >
      <SubsectionHeader
        titleId="analysis-available-records-title"
        title="可分析紀錄"
        description="選擇紀錄後會自動帶入並掃描影像目錄；也可切換成手動填寫。"
      >
        <Button
          disabled={!selectedRecordId}
          onClick={() => void onSelect("")}
        >
          <FiEdit3
            className="size-4 shrink-0"
            aria-hidden="true"
          />
          手動填寫
        </Button>
      </SubsectionHeader>

      <div
        className="max-h-80 min-h-0 overflow-y-auto overscroll-contain rounded-[22px] border border-white/10 bg-white/[0.04] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-300"
        aria-label="可分析紀錄清單"
        role="list"
        tabIndex={0}
      >
        {availableSources.length ? availableSources.map((source) => {
          const selected = source.record_id === selectedRecordId;

          return (
            <article
              className="grid min-w-0 grid-cols-[minmax(0,1fr)_auto] items-start gap-3 border-b border-white/10 p-4 last:border-b-0 max-[720px]:grid-cols-1"
              key={source.record_id}
              role="listitem"
            >
              <div className="grid min-w-0 gap-3">
                <div className="flex min-w-0 flex-wrap items-center gap-2">
                  <h3 className="m-0 min-w-0 break-all text-sm font-black tracking-widest text-white">
                    {source.record_id || "未命名紀錄"}
                  </h3>
                  <StatusPill tone="success">可分析</StatusPill>
                  {selected ? (
                    <StatusPill tone="success">已帶入</StatusPill>
                  ) : null}
                </div>

                <dl className="grid min-w-0 gap-2 text-sm min-[520px]:grid-cols-2 min-[900px]:grid-cols-4">
                  <div className="min-w-0">
                    <dt className="text-xs font-black text-neutral-500">
                      建立時間
                    </dt>
                    <dd className="mt-1 m-0 font-bold text-neutral-200">
                      {formatDateTime(source.created_at)}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-xs font-black text-neutral-500">
                      俯視影像
                    </dt>
                    <dd className="mt-1 m-0 font-bold text-neutral-200">
                      {source.top_frame_count} 張
                    </dd>
                  </div>
                  <div>
                    <dt className="text-xs font-black text-neutral-500">
                      側視影像
                    </dt>
                    <dd className="mt-1 m-0 font-bold text-neutral-200">
                      {source.side_frame_count} 張
                    </dd>
                  </div>
                  <div>
                    <dt className="text-xs font-black text-neutral-500">
                      可配對影格
                    </dt>
                    <dd className="mt-1 m-0 font-bold text-neutral-200">
                      {source.pairable_frame_count} / {source.total_frame_count} 組
                    </dd>
                  </div>
                </dl>
              </div>

              <Button
                className="max-[720px]:w-full"
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
                {selected ? "已帶入" : "帶入目錄"}
              </Button>
            </article>
          );
        }) : (
          <p
            className="m-0 p-4 text-center text-sm font-semibold text-neutral-400"
            role="listitem"
          >
            尚無可分析紀錄，可直接手動填寫影像目錄。
          </p>
        )}
      </div>
    </section>
  );
}

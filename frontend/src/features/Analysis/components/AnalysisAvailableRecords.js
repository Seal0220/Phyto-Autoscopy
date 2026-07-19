import {
  FiCheckCircle,
  FiEdit3,
  FiPlusCircle,
} from "react-icons/fi";

import Button from "@/components/buttons/Button";
import SubsectionHeader from "@/components/headers/SubsectionHeader";
import InnerPanel from "@/components/panels/InnerPanel";
import { StatusPill } from "@/components/panels/Panel";
import { formatDateTime } from "@/lib/formatUtils";

function calibrationLabel(status) {
  if (["valid", "ready"].includes(status)) return "校正有效";
  if (!status || status === "missing") return "缺少有效校正";
  return "校正未就緒";
}

export default function AnalysisAvailableRecords({
  selectedRecordId,
  sources,
  onSelect,
}) {
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
        className="grid max-h-80 gap-3 overflow-y-auto overscroll-contain pr-1 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-300"
        aria-label="可分析紀錄清單"
        role="list"
        tabIndex={0}
      >
        {sources.length ? sources.map((source) => {
          const selected = source.record_id === selectedRecordId;

          return (
            <InnerPanel
              as="article"
              className="grid-cols-[minmax(0,1fr)_auto] items-start max-[720px]:grid-cols-1"
              key={source.record_id}
              role="listitem"
            >
              <div className="grid min-w-0 gap-3">
                <div className="flex min-w-0 flex-wrap items-center gap-2">
                  <h3 className="m-0 min-w-0 break-all text-sm font-black tracking-widest text-white">
                    {source.record_id || "未命名紀錄"}
                  </h3>
                  <StatusPill tone={source.ready ? "success" : "warning"}>
                    {source.ready ? "可分析" : "尚未就緒"}
                  </StatusPill>
                  <StatusPill
                    tone={[
                      "valid",
                      "ready",
                    ].includes(source.calibration_status)
                      ? "success"
                      : "neutral"
                    }
                  >
                    {calibrationLabel(source.calibration_status)}
                  </StatusPill>
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
                disabled={!source.ready || selected}
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
            </InnerPanel>
          );
        }) : (
          <InnerPanel role="listitem">
            <p className="m-0 py-4 text-center text-sm font-semibold text-neutral-400">
              尚無捕捉紀錄，可直接手動填寫影像目錄。
            </p>
          </InnerPanel>
        )}
      </div>
    </section>
  );
}

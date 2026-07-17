import { FiPlusCircle } from "react-icons/fi";

import Button from "@/components/buttons/Button";
import InnerPanel from "@/components/panels/InnerPanel";
import {
  Panel,
  PanelHeader,
  StatusPill,
} from "@/components/panels/Panel";
import { formatDateTime } from "@/lib/formatUtils";

function calibrationLabel(status) {
  if (["valid", "ready"].includes(status)) return "校正有效";
  if (!status || status === "missing") return "缺少有效校正";
  return "校正未就緒";
}

export default function AnalysisDashboardSources({
  sources,
  onCreate,
}) {
  return (
    <Panel aria-label="可分析紀錄">
      <PanelHeader title="可分析紀錄" />
      <div className="grid gap-3 p-5 max-sm:p-4">
        {sources.length ? sources.map((source) => (
          <InnerPanel
            as="article"
            className="grid-cols-[minmax(0,1fr)_auto] items-start max-[720px]:grid-cols-1"
            key={source.record_id}
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
                  tone={["valid", "ready"].includes(source.calibration_status)
                    ? "success"
                    : "neutral"
                  }
                >
                  {calibrationLabel(source.calibration_status)}
                </StatusPill>
              </div>

              <dl className="grid min-w-0 gap-2 text-sm min-[520px]:grid-cols-2 min-[900px]:grid-cols-4">
                <div className="min-w-0">
                  <dt className="text-xs font-black text-neutral-500">建立時間</dt>
                  <dd className="mt-1 m-0 font-bold text-neutral-200">
                    {formatDateTime(source.created_at)}
                  </dd>
                </div>
                <div>
                  <dt className="text-xs font-black text-neutral-500">俯視影像</dt>
                  <dd className="mt-1 m-0 font-bold text-neutral-200">
                    {source.top_frame_count} 張
                  </dd>
                </div>
                <div>
                  <dt className="text-xs font-black text-neutral-500">側視影像</dt>
                  <dd className="mt-1 m-0 font-bold text-neutral-200">
                    {source.side_frame_count} 張
                  </dd>
                </div>
                <div>
                  <dt className="text-xs font-black text-neutral-500">可配對影格</dt>
                  <dd className="mt-1 m-0 font-bold text-neutral-200">
                    {source.pairable_frame_count} / {source.total_frame_count} 組
                  </dd>
                </div>
              </dl>

              {!source.ready ? (
                <ul className="m-0 grid gap-1 pl-5 text-xs font-semibold text-amber-200">
                  {(source.not_ready_reasons.length
                    ? source.not_ready_reasons
                    : ["此紀錄尚未具備分析條件。"]
                  ).map((reason) => (
                    <li key={reason}>{reason}</li>
                  ))}
                </ul>
              ) : null}
            </div>

            <Button
              className="max-[720px]:w-full"
              variant="primary"
              disabled={!source.ready}
              onClick={() => onCreate(source.record_id)}
            >
              <FiPlusCircle
                className="size-4 shrink-0"
                aria-hidden="true"
              />
              建立分析
            </Button>
          </InnerPanel>
        )) : (
          <InnerPanel>
            <p className="m-0 py-4 text-center text-sm font-semibold text-neutral-400">
              尚無捕捉紀錄。請先在「捕捉」頁完成包含俯視角與側視角影像的紀錄。
            </p>
          </InnerPanel>
        )}
      </div>
    </Panel>
  );
}

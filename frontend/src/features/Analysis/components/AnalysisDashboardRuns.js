import {
  FiDownload,
  FiEdit3,
  FiEye,
  FiRefreshCw,
  FiX,
} from "react-icons/fi";

import ActionRow from "@/components/actions/ActionRow";
import Button from "@/components/buttons/Button";
import InnerPanel from "@/components/panels/InnerPanel";
import {
  Panel,
  PanelHeader,
  StatusPill,
} from "@/components/panels/Panel";
import { formatDateTime } from "@/lib/formatUtils";

import {
  analysisProgressPercent,
  analysisStageLabel,
  analysisStatusMeta,
} from "../lib/analysisUtils";
import AnalysisPoseQuality from "./AnalysisPoseQuality";

function reviewLabel(run) {
  if (run.manual_review_completed) return "人工修正已完成";
  if (["needs_review", "reviewing"].includes(run.status)) return "等待人工修正";
  if (run.parameters?.manual_review_required === false) return "未要求人工修正";
  return "人工修正未完成";
}

export default function AnalysisDashboardRuns({
  runs,
  exportingIds,
  exportFailure,
  onClearExportError,
  onExport,
  onOpen,
  onReview,
  onResults,
}) {
  return (
    <Panel aria-label="分析執行">
      <PanelHeader title="分析執行" />
      <div className="grid gap-3 p-5 max-sm:p-4">
        {exportFailure ? (
          <div
            className="grid gap-3 rounded-xl border border-rose-300/30 bg-rose-500/10 p-3"
            role="alert"
          >
            <p className="m-0 break-all text-sm font-semibold text-rose-200">
              {exportFailure.analysisId}：{exportFailure.message}
            </p>
            <div className="flex flex-wrap justify-end gap-2">
              <Button onClick={onClearExportError}>
                <FiX
                  className="size-4 shrink-0"
                  aria-hidden="true"
                />
                清除錯誤
              </Button>
              <Button
                variant="primary"
                disabled={exportingIds.has(exportFailure.analysisId)}
                onClick={() => onExport(exportFailure.analysisId)}
              >
                <FiRefreshCw
                  className="size-4 shrink-0"
                  aria-hidden="true"
                />
                {exportingIds.has(exportFailure.analysisId)
                  ? "重新匯出中…"
                  : "重新匯出"
                }
              </Button>
            </div>
          </div>
        ) : null}

        {runs.length ? runs.map((run) => {
          const status = analysisStatusMeta(run.status);
          const progress = analysisProgressPercent(run.progress);

          return (
            <InnerPanel
              as="article"
              key={run.analysis_id}
            >
              <div className="flex min-w-0 flex-wrap items-center gap-2">
                <h3 className="m-0 min-w-0 break-all text-sm font-black tracking-widest text-white">
                  {run.analysis_id || "未命名分析"}
                </h3>
                <StatusPill tone={status.tone}>{status.label}</StatusPill>
              </div>

              <dl className="grid min-w-0 gap-3 text-sm min-[520px]:grid-cols-2 min-[900px]:grid-cols-4">
                <div className="min-w-0">
                  <dt className="text-xs font-black text-neutral-500">捕捉紀錄</dt>
                  <dd className="mt-1 m-0 break-all font-bold text-neutral-200">
                    {run.record_id || "—"}
                  </dd>
                </div>
                <div>
                  <dt className="text-xs font-black text-neutral-500">目前階段</dt>
                  <dd className="mt-1 m-0 font-bold text-neutral-200">
                    {analysisStageLabel(run.stage)}
                  </dd>
                </div>
                <div>
                  <dt className="text-xs font-black text-neutral-500">人工修正</dt>
                  <dd className="mt-1 m-0 font-bold text-neutral-200">
                    {reviewLabel(run)}
                  </dd>
                </div>
                <div>
                  <dt className="text-xs font-black text-neutral-500">平均重投影誤差</dt>
                  <dd className="mt-1 m-0 font-bold text-neutral-200">
                    {run.average_reprojection_error_px === null
                      ? "—"
                      : `${run.average_reprojection_error_px.toFixed(3)} px`
                    }
                  </dd>
                </div>
              </dl>

              <div className="grid gap-1.5">
                <div className="flex items-center justify-between gap-3 text-xs font-bold text-neutral-400">
                  <span>{progress}%</span>
                  <span>
                    {run.total_frames > 0
                      ? `${run.current_frame} / ${run.total_frames} 影格`
                      : "尚未建立影格進度"
                    }
                  </span>
                </div>
                <div
                  className="h-2 overflow-hidden rounded-full border border-white/10 bg-black/20"
                  role="progressbar"
                  aria-label={`${run.analysis_id || "分析"}進度`}
                  aria-valuemin="0"
                  aria-valuemax="100"
                  aria-valuenow={progress}
                >
                  <div
                    className="h-full rounded-full bg-emerald-300 transition-[width] duration-200 motion-reduce:transition-none"
                    style={{ width: `${progress}%` }}
                  />
                </div>
              </div>

              <AnalysisPoseQuality
                poses={run.camera_pose_results}
                quality={run.pose_quality}
              />

              {run.last_error ? (
                <div
                  className="rounded-xl border border-rose-300/30 bg-rose-500/10 p-3 text-sm font-semibold text-rose-200"
                  role="alert"
                >
                  {run.last_error}
                </div>
              ) : null}

              <ActionRow className="w-full">
                <Button onClick={() => onOpen(run.analysis_id)}>
                  <FiEye
                    className="size-4 shrink-0"
                    aria-hidden="true"
                  />
                  查看分析
                </Button>
                {["needs_review", "reviewing", "completed"].includes(run.status) ? (
                  <Button
                    variant="primary"
                    onClick={() => onReview(run.analysis_id)}
                  >
                    <FiEdit3
                      className="size-4 shrink-0"
                      aria-hidden="true"
                    />
                    {run.status === "completed" ? "查看修正" : "繼續修正"}
                  </Button>
                ) : null}
                {run.status === "completed" ? (
                  <Button onClick={() => onResults(run.analysis_id)}>
                    <FiEye
                      className="size-4 shrink-0"
                      aria-hidden="true"
                    />
                    查看結果
                  </Button>
                ) : null}
                {run.status === "completed" ? (
                  <Button
                    variant="primary"
                    disabled={exportingIds.has(run.analysis_id)}
                    onClick={() => onExport(run.analysis_id)}
                  >
                    <FiDownload
                      className="size-4 shrink-0"
                      aria-hidden="true"
                    />
                    {exportingIds.has(run.analysis_id)
                      ? "匯出中…"
                      : "匯出結果"
                    }
                  </Button>
                ) : null}
              </ActionRow>

              <p className="m-0 text-right text-xs font-semibold text-neutral-500">
                建立於 {formatDateTime(run.created_at)}
              </p>
            </InnerPanel>
          );
        }) : (
          <InnerPanel>
            <p className="m-0 py-4 text-center text-sm font-semibold text-neutral-400">
              尚無分析執行。
            </p>
          </InnerPanel>
        )}
      </div>
    </Panel>
  );
}

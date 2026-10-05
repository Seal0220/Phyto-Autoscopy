"use client";

import { useState } from "react";
import {
  FiArrowRight,
  FiDownload,
  FiEye,
} from "react-icons/fi";

import Button from "@/components/buttons/Button";
import InformationGrid from "@/components/data/InformationGrid";
import {
  Panel,
  PanelHeader,
  StatusPill,
} from "@/components/panels/Panel";
import { formatDateTime } from "@/lib/formatUtils";
import { needsStereoPoseReview } from "@/features/AnalysisRun/lib/analysisStereoReviewUtils";

import { ANALYSIS_METHODS } from "../analysisConfig";
import {
  analysisProgressPercent,
  analysisStageLabel,
  analysisStatusMeta,
} from "../lib/analysisUtils";

const ACTIVE_STATUSES = new Set(["validating", "processing", "reconstructing", "pausing"]);
const ATTENTION_STATUSES = new Set([
  "draft", "ready", "needs_review", "reviewing", "failed", "cancelled",
]);
const COMPLETED_STATUSES = new Set(["completed", "partially_completed"]);
const FILTERS = [
  { id: "all", label: "全部" },
  { id: "attention", label: "待處理" },
  { id: "active", label: "進行中" },
  { id: "completed", label: "已有結果" },
];

function matchesFilter(
  run,
  filter,
) {
  if (filter === "active") return ACTIVE_STATUSES.has(run.status);
  if (filter === "attention") return ATTENTION_STATUSES.has(run.status);
  if (filter === "completed") return COMPLETED_STATUSES.has(run.status);
  return true;
}

function primaryAction(
  run,
  callbacks,
) {
  if (needsStereoPoseReview(run)) {
    return {
      label: "人工雙鏡頭配對",
      onClick: () => callbacks.onOpen(run.analysis_id),
    };
  }
  if (["needs_review", "reviewing"].includes(run.status)) {
    return {
      label: "人工修正",
      onClick: () => callbacks.onReview(run.analysis_id),
    };
  }
  if (COMPLETED_STATUSES.has(run.status)) {
    return {
      label: "查看結果",
      onClick: () => callbacks.onResults(run.analysis_id),
    };
  }
  const label = ACTIVE_STATUSES.has(run.status)
    ? "查看進度"
    : run.status === "ready"
      ? "前往開始"
      : ["failed", "cancelled"].includes(run.status)
        ? "查看並重試"
        : "查看分析";
  return {
    label,
    onClick: () => callbacks.onOpen(run.analysis_id),
  };
}

export default function AnalysisDashboardRuns({
  runs,
  loading = false,
  exportingIds,
  onExport,
  onOpen,
  onReview,
  onResults,
}) {
  const [filter, setFilter] = useState("all");
  const visibleRuns = runs.filter((run) => matchesFilter(run, filter));
  const callbacks = { onOpen, onReview, onResults };

  return (
    <Panel aria-label="分析紀錄">
      <PanelHeader title="分析紀錄" />

      <div
        className="flex flex-wrap gap-2 border-b border-white/15 px-5 py-3 max-sm:px-4"
        role="group"
        aria-label="篩選分析紀錄"
      >
        {FILTERS.map((item) => {
          const selected = filter === item.id;
          const count = runs.filter((run) => matchesFilter(run, item.id)).length;

          return (
            <button
              className={`min-h-9 cursor-pointer rounded-full border px-3 py-1.5 text-xs font-black transition-[background-color,border-color,color] duration-150 focus-visible:outline-2 focus-visible:outline-emerald-300 ${selected
                ? "border-emerald-200/75 bg-emerald-500/20 text-emerald-100 hover:bg-emerald-400/25"
                : "border-white/15 bg-black/15 text-neutral-300 hover:border-white/25 hover:bg-white/10"
              }`}
              aria-pressed={selected}
              key={item.id}
              onClick={() => setFilter(item.id)}
              type="button"
            >
              {item.label} {loading && runs.length === 0 ? "—" : count}
            </button>
          );
        })}
      </div>

      {visibleRuns.length ? (
        <ul className="m-0 list-none p-0">
          {visibleRuns.map((run) => {
            const status = analysisStatusMeta(run.status);
            const progress = analysisProgressPercent(run.progress);
            const action = primaryAction(run, callbacks);
            const completed = COMPLETED_STATUSES.has(run.status);

            return (
              <li
                className="grid min-w-0 gap-3 border-b border-white/10 px-5 py-4 last:border-b-0 max-sm:px-4"
                key={run.analysis_id}
              >
                <div className="flex min-w-0 flex-wrap items-center gap-2">
                  <h3 className="m-0 min-w-0 break-all text-sm font-black text-white">
                    {run.analysis_id || "未命名分析"}
                  </h3>
                  <StatusPill tone={status.tone}>{status.label}</StatusPill>
                </div>

                <InformationGrid
                  items={[
                    { label: "捕捉紀錄", value: run.record_id || "—", truncate: true },
                    {
                      label: "分析方法",
                      value: ANALYSIS_METHODS[run.method_name]?.label || "尚無資料",
                      truncate: true,
                    },
                    {
                      label: "目前階段",
                      value: analysisStageLabel(run.stage),
                      truncate: true,
                    },
                    {
                      label: "建立時間",
                      value: formatDateTime(run.created_at),
                      truncate: true,
                    },
                  ]}
                  border="none"
                  rows={2}
                  stackAtSmall
                />

                {ACTIVE_STATUSES.has(run.status) ? (
                  <div className="grid gap-1.5">
                    <div className="flex items-center justify-between gap-2 text-xs font-bold text-neutral-400">
                      <span>處理進度</span>
                      <span>{progress}% · {run.current_frame || 0} / {run.total_frames || 0} 輪</span>
                    </div>
                    <div
                      className="h-1.5 overflow-hidden rounded-full bg-black/25"
                      role="progressbar"
                      aria-label={`${run.analysis_id || "分析"}進度`}
                      aria-valuemin={0}
                      aria-valuemax={100}
                      aria-valuenow={progress}
                    >
                      <div
                        className="h-full rounded-full bg-emerald-300 transition-[width] duration-200 motion-reduce:transition-none"
                        style={{ width: `${progress}%` }}
                      />
                    </div>
                  </div>
                ) : null}

                {run.last_error ? (
                  <p className="m-0 text-xs font-semibold text-rose-200">
                    {run.last_error}
                  </p>
                ) : null}

                <div className="flex flex-wrap items-center justify-end gap-2">
                  {completed ? (
                    <Button
                      className="min-h-9 px-3 text-xs"
                      disabled={exportingIds.has(run.analysis_id)}
                      onClick={() => onExport(run.analysis_id)}
                    >
                      <FiDownload
                        className="size-3.5 shrink-0"
                        aria-hidden="true"
                      />
                      {exportingIds.has(run.analysis_id) ? "匯出中…" : "匯出"}
                    </Button>
                  ) : null}
                  {[
                    "needs_review", "reviewing", "completed", "partially_completed",
                  ].includes(run.status) ? (
                    <Button
                      className="min-h-9 px-3 text-xs"
                      onClick={() => onOpen(run.analysis_id)}
                    >
                      <FiEye
                        className="size-3.5 shrink-0"
                        aria-hidden="true"
                      />
                      詳情
                    </Button>
                  ) : null}
                  <Button
                    className="min-h-9 px-3 text-xs"
                    variant="primary"
                    onClick={action.onClick}
                  >
                    <FiArrowRight
                      className="size-3.5 shrink-0"
                      aria-hidden="true"
                    />
                    {action.label}
                  </Button>
                </div>
              </li>
            );
          })}
        </ul>
      ) : (
        <p
          className="m-0 px-5 py-10 text-center text-sm font-semibold text-neutral-400"
          role="status"
        >
          {loading && runs.length === 0
            ? "讀取分析紀錄中…"
            : runs.length
              ? "此分類尚無分析紀錄。"
              : "尚無已建立的分析；已捕捉的資料請點「新增分析」選擇紀錄。"
          }
        </p>
      )}
    </Panel>
  );
}

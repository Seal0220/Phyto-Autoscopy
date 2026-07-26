"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import {
  FiRefreshCw,
} from "react-icons/fi";
import { PiHouseFill } from "react-icons/pi";

import Button from "@/components/buttons/Button";
import StatusCard from "@/components/cards/StatusCard";
import {
  Panel,
  PanelHeader,
  StatusPill,
} from "@/components/panels/Panel";
import useNotificationsContext from "@/features/Notifications/hooks/useNotificationsContext";

import AnalysisRunActions from "./components/AnalysisRunActions";
import AnalysisRunMetadata from "./components/AnalysisRunMetadata";
import AnalysisRunRoundOverview from "./components/AnalysisRunRoundOverview";
import useAnalysisRun from "./hooks/useAnalysisRun";
import {
  analysisRunDisplay,
} from "./lib/analysisRunUtils";

export default function AnalysisRun({
  analysisId,
}) {
  const router = useRouter();
  const { showNotification } = useNotificationsContext();
  const {
    run,
    progress,
    formalData,
    loading,
    loadError,
    pendingAction,
    mutationError,
    mutationOutcomeUnknown,
    exportPending,
    exportError,
    socketError,
    load,
    performAction,
    downloadExport,
    resetSocketError,
  } = useAnalysisRun({
    analysisId,
  });

  useEffect(() => {
    if (loadError) showNotification(loadError, "error");
  }, [
    loadError,
    showNotification,
  ]);

  useEffect(() => {
    if (mutationError) showNotification(mutationError, "error");
  }, [
    mutationError,
    showNotification,
  ]);

  useEffect(() => {
    if (exportError) showNotification(exportError, "error");
  }, [
    exportError,
    showNotification,
  ]);

  useEffect(() => {
    if (!socketError) return;
    showNotification(socketError.message, "error");
    resetSocketError();
  }, [
    resetSocketError,
    showNotification,
    socketError,
  ]);
  const hasMatchingProgress = Boolean(
    run
    && progress?.analysis_id
    && progress.analysis_id === run.analysis_id,
  );
  const effectiveRun = run
    ? {
      ...run,
      status: hasMatchingProgress
        && progress.status
        && progress.status !== "idle"
        ? progress.status
        : run.status,
      stage: hasMatchingProgress && progress.stage
        ? progress.stage
        : run.stage,
      progress: hasMatchingProgress
        ? progress.progress
        : run.progress,
      current_frame: hasMatchingProgress
        ? progress.current_frame
        : run.current_frame,
      total_frames: hasMatchingProgress
        ? progress.total_frames
        : run.total_frames,
      last_error: hasMatchingProgress && progress.last_error
        ? progress.last_error
        : run.last_error,
    }
    : null;
  const display = analysisRunDisplay(effectiveRun);
  const locked = Boolean(pendingAction) || mutationOutcomeUnknown;

  return (
    <div className="mx-auto grid w-full max-w-[112.5rem] gap-4 pt-24 max-[980px]:pt-32">
        <Panel aria-label="分析紀錄詳情">
          <PanelHeader
            title="分析紀錄"
            action={(
              <div className="flex flex-wrap items-center justify-end gap-2">
                <Button
                  disabled={loading}
                  onClick={() => void load({
                    confirmMutation: mutationOutcomeUnknown,
                  })}
                >
                  <FiRefreshCw
                    className="size-4 shrink-0"
                    aria-hidden="true"
                  />
                  {loading ? "讀取中…" : "重新讀取"}
                </Button>
                <Button
                  disabled={Boolean(pendingAction)}
                  onClick={() => router.push("/analysis")}
                >
                  <PiHouseFill
                    className="size-4 shrink-0"
                    aria-hidden="true"
                  />
                  返回分析首頁
                </Button>
              </div>
            )}
          />

          <div className="grid gap-4 p-5 max-sm:p-4">
            {loading && !effectiveRun ? (
              <div
                className="grid min-h-36 place-items-center rounded-xl border border-white/15 bg-black/15 p-4 text-sm font-semibold text-neutral-400"
                role="status"
              >
                讀取分析紀錄中…
              </div>
            ) : null}

            {effectiveRun ? (
              <>
                <div className="grid gap-3 min-[520px]:grid-cols-2 min-[900px]:grid-cols-4">
                  <StatusCard
                    title="執行狀態"
                    content={display.status.label}
                    note={effectiveRun.analysis_id}
                  />
                  <StatusCard
                    title="目前階段"
                    content={display.stage}
                    note={effectiveRun.stage || "—"}
                  />
                  <StatusCard
                    title="分析進度"
                    content={`${display.progressPercent}%`}
                    note={`${effectiveRun.current_frame} / ${effectiveRun.total_frames} 輪`}
                  />
                  <StatusCard
                    title="人工檢查"
                    content={effectiveRun.manual_review_completed ? "已完成" : "未完成"}
                    note={effectiveRun.status === "needs_review" ? "等待修正" : "分析紀錄"}
                  />
                </div>

                <div className="grid gap-2">
                  <div className="flex items-center justify-between gap-3 text-xs font-black text-neutral-400">
                    <span>執行進度</span>
                    <StatusPill tone={display.status.tone}>
                      {display.status.label}
                    </StatusPill>
                  </div>
                  <div
                    className="h-2 overflow-hidden rounded-full border border-white/15 bg-black/20"
                    role="progressbar"
                    aria-label="分析進度"
                    aria-valuemin={0}
                    aria-valuemax={100}
                    aria-valuenow={display.progressPercent}
                  >
                    <div
                      className="h-full rounded-full bg-emerald-300 transition-[width] duration-150 motion-reduce:transition-none"
                      style={{ width: `${display.progressPercent}%` }}
                    />
                  </div>
                </div>

                {effectiveRun.last_error ? (
                  <div
                    className="rounded-xl border border-rose-300/30 bg-rose-500/10 p-3 text-sm font-semibold text-rose-200"
                    role="alert"
                  >
                    {effectiveRun.last_error}
                  </div>
                ) : null}

                <AnalysisRunMetadata
                  formalData={formalData}
                  run={effectiveRun}
                />

                <AnalysisRunRoundOverview formalData={formalData} />

                <AnalysisRunActions
                  exportPending={exportPending}
                  locked={locked}
                  pendingAction={pendingAction}
                  status={effectiveRun.status}
                  onAction={(action) => void performAction(action)}
                  onExport={() => void downloadExport()}
                  onOpenReview={() => router.push(
                    `/analysis/${encodeURIComponent(analysisId)}/review`,
                  )}
                  onOpenResults={() => router.push(
                    `/analysis/${encodeURIComponent(analysisId)}/results`,
                  )}
                  onSkipReview={() => {
                    const confirmed = window.confirm(
                      "略過後將直接採用目前的自動尖端標記結果，並記錄此次未完成人工確認。確定繼續嗎？",
                    );
                    if (confirmed) {
                      void performAction("reconstruct_without_review");
                    }
                  }}
                />
              </>
            ) : null}
          </div>
        </Panel>
    </div>
  );
}

"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import {
  FiArrowLeft,
  FiRefreshCw,
  FiX,
} from "react-icons/fi";

import Button from "@/components/buttons/Button";
import StatusCard from "@/components/cards/StatusCard";
import RetryMessage from "@/components/feedback/RetryMessage";
import {
  Panel,
  PanelHeader,
  StatusPill,
} from "@/components/panels/Panel";
import MainNavigation from "@/features/MainNavigation/MainNavigation";
import useNotificationsContext from "@/features/Notifications/hooks/useNotificationsContext";

import AnalysisRunActions from "./components/AnalysisRunActions";
import AnalysisRunMetadata from "./components/AnalysisRunMetadata";
import useAnalysisRun from "./hooks/useAnalysisRun";
import { analysisRunDisplay } from "./lib/analysisRunUtils";

export default function AnalysisRun({
  analysisId,
}) {
  const router = useRouter();
  const { showNotification } = useNotificationsContext();
  const {
    run,
    progress,
    framePairs,
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
    clearMutationError,
    clearExportError,
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
    <main className="min-h-screen bg-[#06100c] px-5 pb-8 max-sm:px-3">
      <MainNavigation />

      <div className="mx-auto grid w-full max-w-[112.5rem] gap-4 pt-[5.6rem] max-[980px]:pt-[8.8rem]">
        <Panel aria-label="分析執行詳情">
          <PanelHeader
            title="分析執行"
            action={(
              <Button
                disabled={Boolean(pendingAction)}
                onClick={() => router.push("/analysis")}
              >
                <FiArrowLeft
                  className="size-4 shrink-0"
                  aria-hidden="true"
                />
                返回分析首頁
              </Button>
            )}
          />

          <div className="grid gap-4 p-5 max-sm:p-4">
            {loadError ? (
              <RetryMessage
                message={loadError}
                onRetry={() => void load()}
                retrying={loading}
              />
            ) : null}

            {socketError ? (
              <div
                className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-3 rounded-xl border border-amber-200/25 bg-amber-500/10 p-3"
                role="status"
              >
                <p className="m-0 text-sm font-semibold text-amber-200">
                  {socketError.message} 分析進度仍會定時重新讀取。
                </p>
                <Button onClick={resetSocketError}>
                  <FiX
                    className="size-4 shrink-0"
                    aria-hidden="true"
                  />
                  清除提示
                </Button>
              </div>
            ) : null}

            {loading && !effectiveRun ? (
              <div
                className="grid min-h-36 place-items-center rounded-xl border border-white/10 bg-black/10 p-4 text-sm font-semibold text-neutral-400"
                role="status"
              >
                讀取分析執行中…
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
                    note={`${effectiveRun.current_frame} / ${effectiveRun.total_frames} 影格`}
                  />
                  <StatusCard
                    title="人工檢查"
                    content={effectiveRun.manual_review_completed ? "已完成" : "未完成"}
                    note={effectiveRun.status === "needs_review" ? "等待修正" : "分析執行"}
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
                    className="h-2 overflow-hidden rounded-full border border-white/10 bg-black/20"
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

                {mutationError ? (
                  <div
                    className="grid gap-3 rounded-xl border border-rose-300/30 bg-rose-500/10 p-3"
                    role="alert"
                  >
                    <p className="m-0 text-sm font-semibold text-rose-200">
                      {mutationError}
                    </p>
                    <div className="flex flex-wrap justify-end gap-2">
                      {mutationOutcomeUnknown ? (
                        <Button
                          disabled={loading}
                          onClick={() => void load({ confirmMutation: true })}
                        >
                          <FiRefreshCw
                            className="size-4 shrink-0"
                            aria-hidden="true"
                          />
                          重新讀取並確認
                        </Button>
                      ) : (
                        <Button onClick={clearMutationError}>
                          <FiX
                            className="size-4 shrink-0"
                            aria-hidden="true"
                          />
                          清除錯誤
                        </Button>
                      )}
                    </div>
                  </div>
                ) : null}

                {exportError ? (
                  <div
                    className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-3 rounded-xl border border-rose-300/30 bg-rose-500/10 p-3"
                    role="alert"
                  >
                    <p className="m-0 text-sm font-semibold text-rose-200">
                      {exportError}
                    </p>
                    <Button onClick={clearExportError}>
                      <FiX
                        className="size-4 shrink-0"
                        aria-hidden="true"
                      />
                      清除錯誤
                    </Button>
                  </div>
                ) : null}

                <AnalysisRunMetadata
                  framePairs={framePairs}
                  run={effectiveRun}
                />

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
                      "略過後將直接使用自動、估計與插值結果進行三維重建，並記錄此次未完成人工修正。確定繼續嗎？",
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
    </main>
  );
}

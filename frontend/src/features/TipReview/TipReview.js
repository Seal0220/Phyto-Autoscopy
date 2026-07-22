"use client";

import {
  useEffect,
} from "react";
import { useRouter } from "next/navigation";
import {
  FiArrowLeft,
  FiCheck,
  FiRefreshCw,
  FiRotateCcw,
  FiSave,
  FiTrash2,
  FiX,
} from "react-icons/fi";

import ActionRow from "@/components/actions/ActionRow";
import Button from "@/components/buttons/Button";
import RetryMessage from "@/components/feedback/RetryMessage";
import { TextInput } from "@/components/inputs/Input";
import { ToggleRow } from "@/components/inputs/Toggle";
import InnerPanel from "@/components/panels/InnerPanel";
import {
  Panel,
  PanelHeader,
  StatusPill,
} from "@/components/panels/Panel";
import { analysisRunDisplay } from "@/features/AnalysisRun/lib/analysisRunUtils";
import useNotificationsContext from "@/features/Notifications/hooks/useNotificationsContext";

import TipReviewCanvas from "./components/TipReviewCanvas";
import TipReviewControls from "./components/TipReviewControls";
import TipReviewCorrectionHistory from "./components/TipReviewCorrectionHistory";
import useTipReview from "./hooks/useTipReview";

function isTextEditingTarget(target) {
  return target instanceof HTMLElement && (
    ["A", "BUTTON", "INPUT", "TEXTAREA", "SELECT"].includes(target.tagName)
    || target.isContentEditable
  );
}

export default function TipReview({
  analysisId,
}) {
  const router = useRouter();
  const { showNotification } = useNotificationsContext();
  const {
    run,
    frameIds,
    indexedFrameCount,
    currentFrameId,
    frame,
    frameCorrections,
    drafts,
    activeCamera,
    playing,
    loading,
    loadError,
    frameLoading,
    frameError,
    pendingAction,
    mutationError,
    mutationOutcomeUnknown,
    loadIndex,
    loadFrame,
    goRelative,
    goToFrame,
    setActiveCamera,
    setPlaying,
    updateDraft,
    saveActiveCorrection,
    removeCorrection,
    clearActiveCorrection,
    reconstruct,
    confirmMutationOutcome,
    clearMutationError,
  } = useTipReview({
    analysisId,
  });
  const activeDraft = drafts[activeCamera];
  const locked = Boolean(pendingAction) || mutationOutcomeUnknown;
  const editingLocked = locked
    || frameLoading
    || !frame
    || frame.pair.frame_id !== currentFrameId;

  useEffect(() => {
    const error = mutationError || frameError || loadError;
    if (error) showNotification(error, "error");
  }, [
    frameError,
    loadError,
    mutationError,
    showNotification,
  ]);
  const runDisplay = analysisRunDisplay(run);

  useEffect(() => {
    function handleKeyDown(event) {
      if (isTextEditingTarget(event.target)) return;

      if (event.key === "ArrowLeft") {
        event.preventDefault();
        goRelative(-1);
      } else if (event.key === "ArrowRight") {
        event.preventDefault();
        goRelative(1);
      } else if (event.code === "Space") {
        event.preventDefault();
        if (!event.repeat) setPlaying(!playing);
      } else if (event.key.toLowerCase() === "t") {
        setActiveCamera("top");
      } else if (event.key.toLowerCase() === "s") {
        setActiveCamera("side");
      } else if (event.key.toLowerCase() === "r" && !event.repeat) {
        event.preventDefault();
        if (!editingLocked) void clearActiveCorrection();
      } else if (event.key.toLowerCase() === "x" && !event.repeat) {
        event.preventDefault();
        if (!editingLocked) {
          updateDraft(activeCamera, {
            invalid: !drafts[activeCamera]?.invalid,
          });
        }
      } else if (event.key === "Enter" && !event.repeat) {
        event.preventDefault();
        if (!editingLocked) void saveActiveCorrection({ advance: true });
      }
    }

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [
    activeCamera,
    clearActiveCorrection,
    drafts,
    editingLocked,
    goRelative,
    playing,
    saveActiveCorrection,
    setActiveCamera,
    setPlaying,
    updateDraft,
  ]);

  return (
    <div className="mx-auto grid w-full max-w-[112.5rem] gap-4 pt-24 max-[980px]:pt-32">
        <Panel aria-label="植物尖端人工修正">
          <PanelHeader
            title="人工修正"
            action={(
              <div className="flex flex-wrap items-center justify-end gap-2">
                {run ? (
                  <StatusPill tone={runDisplay.status.tone}>
                    {runDisplay.status.label}
                  </StatusPill>
                ) : null}
                <Button
                  disabled={Boolean(pendingAction)}
                  onClick={() => router.push(
                    `/analysis/${encodeURIComponent(analysisId)}`,
                  )}
                >
                  <FiArrowLeft
                    className="size-4 shrink-0"
                    aria-hidden="true"
                  />
                  返回分析紀錄
                </Button>
              </div>
            )}
          />

          <div className="grid gap-4 p-5 max-sm:p-4">
            {loadError ? (
              <RetryMessage
                message={loadError}
                onRetry={() => void loadIndex()}
                retrying={loading}
              />
            ) : null}

            {loading && frameIds.length === 0 ? (
              <div
                className="grid min-h-36 place-items-center rounded-xl border border-white/15 bg-black/15 p-4 text-sm font-semibold text-neutral-400"
                role="status"
              >
                讀取人工修正資料中…
              </div>
            ) : null}

            {!loading && !loadError && frameIds.length === 0 ? (
              <div className="rounded-xl border border-dashed border-white/15 bg-black/15 p-5 text-center text-sm font-semibold text-neutral-400">
                此分析紀錄尚無可檢查影格。
              </div>
            ) : null}

            {frameIds.length > 0 ? (
              <>
                <TipReviewControls
                  activeCamera={activeCamera}
                  currentFrameId={currentFrameId}
                  frame={frame}
                  frameIds={frameIds}
                  frameLoading={frameLoading}
                  playing={playing}
                  onActiveCameraChange={setActiveCamera}
                  onFrameJump={goToFrame}
                  onNext={() => goRelative(1)}
                  onPlayingChange={setPlaying}
                  onPrevious={() => goRelative(-1)}
                />

                {indexedFrameCount !== frameIds.length ? (
                  <p className="m-0 rounded-xl border border-amber-200/25 bg-amber-500/10 p-3 text-xs font-semibold text-amber-200">
                    影格索引與配對清單數量不同；目前依配對清單導覽，請確認分析輸出完整性。
                  </p>
                ) : null}

                {frameError ? (
                  <RetryMessage
                    message={frameError}
                    onRetry={() => void loadFrame()}
                    retrying={frameLoading}
                  />
                ) : null}

                {frame ? (
                  <div className="grid gap-3 min-[900px]:grid-cols-2">
                    <TipReviewCanvas
                      active={activeCamera === "top"}
                      cameraId="top"
                      disabled={editingLocked}
                      draft={drafts.top}
                      imageUrl={frame.topImageUrl}
                      storedDetection={frame.topDetection}
                      onActivate={setActiveCamera}
                      onPointChange={(
                        cameraId,
                        point,
                      ) => updateDraft(cameraId, {
                        point,
                        invalid: false,
                      })}
                    />
                    <TipReviewCanvas
                      active={activeCamera === "side"}
                      cameraId="side"
                      disabled={editingLocked}
                      draft={drafts.side}
                      imageUrl={frame.sideImageUrl}
                      storedDetection={frame.sideDetection}
                      onActivate={setActiveCamera}
                      onPointChange={(
                        cameraId,
                        point,
                      ) => updateDraft(cameraId, {
                        point,
                        invalid: false,
                      })}
                    />
                  </div>
                ) : null}

                <div className="grid gap-4 min-[900px]:grid-cols-2">
                  <InnerPanel>
                    <div className="flex min-w-0 flex-wrap items-center justify-between gap-2">
                      <h3 className="m-0 text-base font-black tracking-widest text-white">
                        {activeCamera === "top" ? "俯視角修正" : "側視角修正"}
                      </h3>
                      <StatusPill tone={activeDraft?.dirty ? "warning" : "neutral"}>
                        {activeDraft?.dirty ? "尚未儲存" : "已同步"}
                      </StatusPill>
                    </div>

                    <TextInput
                      id={`tip-review-reason-${activeCamera}`}
                      label="修正原因"
                      value={activeDraft?.reason || ""}
                      disabled={editingLocked}
                      maxLength={500}
                      onValueChange={(reason) => updateDraft(activeCamera, {
                        reason,
                      })}
                    />

                    <ToggleRow
                      checked={Boolean(activeDraft?.invalid)}
                      label="標記為無效"
                      description="此標記只影響目前影格的所選視角；原始自動偵測資料仍保留。"
                      disabled={editingLocked}
                      onClick={() => updateDraft(activeCamera, {
                        invalid: !activeDraft?.invalid,
                      })}
                    />

                    <p className="m-0 text-xs font-semibold text-neutral-400">
                      人工修正會另行保存，自動與估計的原始結果永不被覆寫。
                    </p>

                    <ActionRow className="w-full">
                      <Button
                        variant="dangerGhost"
                        disabled={editingLocked}
                        onClick={() => void clearActiveCorrection()}
                      >
                        <FiTrash2
                          className="size-4 shrink-0"
                          aria-hidden="true"
                        />
                        清除最新修正（R）
                      </Button>
                      <Button
                        className="ml-auto"
                        variant="primary"
                        disabled={editingLocked || !activeDraft}
                        onClick={() => void saveActiveCorrection()}
                      >
                        <FiSave
                          className="size-4 shrink-0"
                          aria-hidden="true"
                        />
                        {pendingAction === `save-${activeCamera}` ? "儲存中…" : "儲存修改"}
                      </Button>
                    </ActionRow>
                  </InnerPanel>

                  <TipReviewCorrectionHistory
                    corrections={frameCorrections}
                    deletingId={pendingAction.startsWith("delete-")
                      ? pendingAction.slice(7)
                      : ""
                    }
                    locked={editingLocked}
                    onDelete={(correctionId) => void removeCorrection(correctionId)}
                  />
                </div>

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
                          disabled={Boolean(pendingAction)}
                          onClick={() => void confirmMutationOutcome()}
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

                {run && ["needs_review", "reviewing", "completed"].includes(run.status) ? (
                  <ActionRow className="w-full">
                    <Button
                      disabled={Boolean(pendingAction)}
                      onClick={() => router.push(
                        `/analysis/${encodeURIComponent(analysisId)}`,
                      )}
                    >
                      <FiArrowLeft
                        className="size-4 shrink-0"
                        aria-hidden="true"
                      />
                      返回執行詳情
                    </Button>
                    <Button
                      className="ml-auto"
                      variant="primary"
                      disabled={locked}
                      onClick={async () => {
                        const started = await reconstruct();
                        if (started) {
                          router.push(`/analysis/${encodeURIComponent(analysisId)}`);
                        }
                      }}
                    >
                      {pendingAction === "reconstruct" ? (
                        <FiRotateCcw
                          className="size-4 shrink-0"
                          aria-hidden="true"
                        />
                      ) : (
                        <FiCheck
                          className="size-4 shrink-0"
                          aria-hidden="true"
                        />
                      )}
                      {pendingAction === "reconstruct" ? "啟動重建中…" : "完成修正並重建"}
                    </Button>
                  </ActionRow>
                ) : null}
              </>
            ) : null}
          </div>
        </Panel>
    </div>
  );
}

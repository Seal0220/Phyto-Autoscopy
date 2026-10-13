"use client";

import { useState } from "react";
import { FiEdit2 } from "react-icons/fi";
import ActionRow from "@/components/actions/ActionRow";
import Button from "@/components/buttons/Button";
import RetryMessage from "@/components/feedback/RetryMessage";

import InformationGrid from "@/components/data/InformationGrid";
import SubsectionHeader from "@/components/headers/SubsectionHeader";
import { StatusPill } from "@/components/panels/Panel";
import { ANALYSIS_MODEL_STATUS_META } from "@/features/Analysis/analysisConfig";
import { formatDisplayMessage, formatNumberWithUnit } from "@/lib/formatUtils";

import { analysisRoundStatus } from "../lib/analysisRunUtils";
import AnalysisRunModelPreview from "./AnalysisRunModelPreview";
import AnalysisRunRoundImages from "./AnalysisRunRoundImages";
import useAnalysisRunRoundRetry from "../hooks/useAnalysisRunRoundRetry";

export default function AnalysisRunRoundDetail({
  analysisId,
  round,
  model,
  landmark,
  correction,
  busy,
  onReloadRun,
}) {
  const [marking, setMarking] = useState(false);
  const [controlsElement, setControlsElement] = useState(null);
  const [featureActionElement, setFeatureActionElement] = useState(null);
  const [tipActionElement, setTipActionElement] = useState(null);
  const retry = useAnalysisRunRoundRetry({
    analysisId,
    roundKey: round.round_key,
    onAccepted: onReloadRun,
  });
  const status = analysisRoundStatus(round.status, {
    model,
    landmark,
    correction,
  });
  const measurementPending = !landmark?.valid && model?.status === "completed"
    && ["alignment_pending", "tip_only", "tip_invalid"].includes(round.status);
  const modelStatus = ANALYSIS_MODEL_STATUS_META[model?.status] || {
    label: "尚無模型",
    tone: "neutral",
  };

  return (
    <div className="grid h-full min-h-0 min-w-0 grid-rows-[minmax(0,1fr)_auto]">
      <div
        role="region"
        aria-label="本輪內容"
        tabIndex={0}
        className="min-h-0 min-w-0 overflow-x-hidden overflow-y-auto overscroll-contain p-4 focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-emerald-300 [scrollbar-gutter:stable] max-sm:p-2"
      >
        <div className="grid min-w-0 content-start gap-4">
          <SubsectionHeader
            title={(
              <span className="flex min-w-0 flex-wrap items-center gap-2">
                <span className="min-w-0 break-all">{round.mode_id} · {round.round_id}</span>
                <StatusPill tone={status.tone}>{status.label}</StatusPill>
                {round.status === "alignment_pending" && model?.status === "alignment_pending" ? null : (
                  <StatusPill tone={modelStatus.tone}>{modelStatus.label}</StatusPill>
                )}
              </span>
            )}
          />
          <InformationGrid
            items={[
              { label: "影像", value: `${round.view_count || 0} 張` },
              { label: "旋臂視角", value: `${round.rotating_view_count || 0} 張` },
              {
                label: "尖端標記",
                value: landmark?.valid
                  ? formatNumberWithUnit(landmark.confidence * 100, "%")
                  : correction?.observations?.length && !correction.invalid ? "已人工標記；待量測校正"
                    : landmark?.image_tip_confirmed ? "已追蹤；待量測校正"
                      : round.status === "waiting_tip_seed" ? "等待第一輪初始化" : landmark ? "待補正" : "尚未處理",
                tone: landmark?.valid || landmark?.image_tip_confirmed || (correction?.observations?.length && !correction.invalid) ? "success" : "warning",
              },
              {
                label: "重投影誤差",
                value: formatNumberWithUnit(landmark?.mean_reprojection_error_px, "px"),
              },
              {
                label: "三維位置（mm）",
                value: landmark?.valid
                  ? [landmark.x_mm, landmark.y_mm, landmark.z_mm]
                    .map((value) => formatNumberWithUnit(value, "").trim()).join(", ")
                  : "尚無可用量測",
              },
              {
                label: "標記來源",
                value: landmark?.manually_corrected ? "人工修正"
                  : landmark?.image_tip_confirmed ? "影像追蹤"
                    : landmark?.valid ? "三維量測" : "尚未確認",
              },
            ]}
            border="none"
            rows={2}
            stackAtSmall
            wrapValues
          />
          {round.failure_reason || model?.failure_reason || landmark?.failure_reason ? (
            <p className={`m-0 break-words text-sm font-semibold ${measurementPending ? "text-neutral-300" : "text-rose-200"}`}>
              {formatDisplayMessage(round.failure_reason || model?.failure_reason || landmark?.failure_reason)}
            </p>
          ) : null}
          {round.status === "waiting_tip_seed" ? (
            <p className="m-0 text-sm text-neutral-300">請在上方「目前處理影像」標記模型、俯視與側視尖端，確認後自動繼續。</p>
          ) : (
            <>
              {retry.error ? (
                <RetryMessage
                  message={retry.error}
                  onRetry={onReloadRun}
                  retrying={busy}
                />
              ) : null}
              <AnalysisRunRoundImages
                analysisId={analysisId}
                round={round}
                hasLandmark={Boolean(landmark)}
                marking={marking}
                correction={correction}
                onSaved={onReloadRun}
                onFinishEditing={() => setMarking(false)}
                model={model}
                landmark={landmark}
                controlsElement={controlsElement}
                featureActionElement={featureActionElement}
                tipActionElement={tipActionElement}
              />
              {model && !marking ? (
                <AnalysisRunModelPreview
                  analysisId={analysisId}
                  model={model}
                  landmark={landmark}
                  correction={correction}
                />
              ) : null}
            </>
          )}
        </div>
      </div>
      {round.status !== "waiting_tip_seed" ? (
        <div
          role="region"
          aria-label="本輪控制列"
          className="grid min-w-0 gap-2 border-t border-white/15 bg-[#102019] p-3 max-sm:p-2"
        >
          <div
            ref={setControlsElement}
            className="min-w-0 overflow-x-auto overscroll-contain"
          />
          <ActionRow
            dividerClassName="hidden"
            className="w-full min-w-0 flex-nowrap! overflow-x-auto overscroll-contain pt-0! [&_button]:shrink-0"
          >
            {!marking ? (
              <Button
                disabled={retry.saving || ["ready", "incomplete"].includes(round.status)}
                onClick={() => setMarking(true)}
              >
                <FiEdit2
                  className="size-4 shrink-0"
                  aria-hidden="true"
                />
                {landmark?.valid || landmark?.image_tip_confirmed || correction?.observations?.length ? "修改尖端" : "標記尖端"}
              </Button>
            ) : null}
            <span
              ref={setTipActionElement}
              className="contents"
            />
            {["failed", "alignment_pending"].includes(round.status) || measurementPending ? (
              <Button
                disabled={marking || busy || retry.saving || retry.unknown}
                onClick={retry.retry}
              >
                {retry.saving ? "重試中…" : measurementPending || round.status === "alignment_pending" ? "重新自動對齊" : "重試本輪"}
              </Button>
            ) : null}
            <span
              ref={setFeatureActionElement}
              className="contents"
            />
          </ActionRow>
        </div>
      ) : null}
    </div>
  );
}

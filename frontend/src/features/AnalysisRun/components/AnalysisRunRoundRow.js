"use client";

import { useState } from "react";
import ActionRow from "@/components/actions/ActionRow";
import Button from "@/components/buttons/Button";
import RetryMessage from "@/components/feedback/RetryMessage";

import InformationGrid from "@/components/data/InformationGrid";
import DisclosurePanel from "@/components/panels/DisclosurePanel";
import { StatusPill } from "@/components/panels/Panel";
import { ANALYSIS_MODEL_STATUS_META } from "@/features/Analysis/analysisConfig";
import { formatNumberWithUnit } from "@/lib/formatUtils";

import { analysisRoundStatus } from "../lib/analysisRunUtils";
import AnalysisRunModelPreview from "./AnalysisRunModelPreview";
import AnalysisRunRoundImages from "./AnalysisRunRoundImages";
import AnalysisRunStereoReview from "./AnalysisRunStereoReview";
import useAnalysisRunRoundRetry from "../hooks/useAnalysisRunRoundRetry";

export default function AnalysisRunRoundRow({
  analysisId,
  round,
  model,
  landmark,
  correction,
  busy,
  onReloadRun,
}) {
  const [open, setOpen] = useState(false);
  const [aligning, setAligning] = useState(false);
  const [marking, setMarking] = useState(false);
  const retry = useAnalysisRunRoundRetry({ analysisId, roundKey: round.round_key, onAccepted: onReloadRun });
  const status = round.status === "tip_invalid" && landmark?.image_tip_confirmed
    ? { label: "待量測校正", tone: "warning" }
    : analysisRoundStatus(round.status);
  const modelStatus = ANALYSIS_MODEL_STATUS_META[model?.status] || {
    label: "尚無模型",
    tone: "neutral",
  };

  return (
    <DisclosurePanel
      open={round.status === "waiting_tip_seed" ? true : undefined}
      title={(
        <span className="flex min-w-0 flex-wrap items-center gap-2">
          <span className="min-w-0 break-all">{round.mode_id} · {round.round_id}</span>
          <StatusPill tone={status.tone}>{status.label}</StatusPill>
          {round.status === "alignment_pending" && model?.status === "alignment_pending" ? null : (
            <StatusPill tone={modelStatus.tone}>{modelStatus.label}</StatusPill>
          )}
        </span>
      )}
      description={`${round.view_count || 0} 張影像 · 展開查看模型與結果`}
      onToggle={(event) => {
        if (event.target !== event.currentTarget) return;
        setOpen(event.currentTarget.open);
      }}
    >
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
        ]}
        border="none"
        rows={2}
        stackAtSmall
      />
      {round.failure_reason || model?.failure_reason || landmark?.failure_reason ? (
        <p className="m-0 break-words text-sm font-semibold text-rose-200">
          {round.failure_reason || model?.failure_reason || landmark?.failure_reason}
        </p>
      ) : null}
      {open || round.status === "waiting_tip_seed" ? (
        <>
          <ActionRow>
            {round.status === "alignment_pending" ? (
              <Button disabled={busy || retry.saving} onClick={() => setAligning((previous) => !previous)}>
                補相機對齊
              </Button>
            ) : null}
            {["failed", "alignment_pending"].includes(round.status) ? (
              <Button disabled={busy || retry.saving || retry.unknown} onClick={retry.retry}>
                {retry.saving ? "重試中…" : "重試本輪"}
              </Button>
            ) : null}
            {round.status !== "waiting_tip_seed" ? <Button
              disabled={retry.saving || ["ready", "incomplete"].includes(round.status)}
              aria-pressed={marking}
              onClick={() => setMarking((previous) => !previous)}
            >
              {marking ? "結束尖端標記" : landmark?.valid || landmark?.image_tip_confirmed || correction?.observations?.length ? "修改尖端" : "標記尖端"}
            </Button> : null}
          </ActionRow>
          {retry.error ? <RetryMessage message={retry.error} onRetry={onReloadRun} retrying={busy} /> : null}
          {aligning && round.status === "alignment_pending" ? (
            <AnalysisRunStereoReview
              analysisId={analysisId}
              roundKey={round.round_key}
              open
              onClose={() => setAligning(false)}
              onAccepted={() => { setAligning(false); void onReloadRun(); }}
              onReloadRun={onReloadRun}
            />
          ) : null}
          <AnalysisRunRoundImages
            analysisId={analysisId}
            round={round}
            hasLandmark={Boolean(landmark)}
            marking={marking || round.status === "waiting_tip_seed"}
            correction={correction}
            onSaved={onReloadRun}
            model={model}
            landmark={landmark}
          />
          {model && !marking && round.status !== "waiting_tip_seed" ? (
            <AnalysisRunModelPreview
              analysisId={analysisId}
              model={model}
              landmark={landmark}
            />
          ) : null}
        </>
      ) : null}
    </DisclosurePanel>
  );
}

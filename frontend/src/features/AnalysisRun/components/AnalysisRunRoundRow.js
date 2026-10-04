"use client";

import { useState } from "react";

import InformationGrid from "@/components/data/InformationGrid";
import DisclosurePanel from "@/components/panels/DisclosurePanel";
import { StatusPill } from "@/components/panels/Panel";
import { ANALYSIS_MODEL_STATUS_META } from "@/features/Analysis/analysisConfig";
import { formatNumberWithUnit } from "@/lib/formatUtils";

import { analysisRoundStatus } from "../lib/analysisRunUtils";
import AnalysisRunRoundImages from "./AnalysisRunRoundImages";

export default function AnalysisRunRoundRow({
  analysisId,
  round,
  model,
  landmark,
}) {
  const [open, setOpen] = useState(false);
  const status = analysisRoundStatus(round.status);
  const modelStatus = ANALYSIS_MODEL_STATUS_META[model?.status] || {
    label: "尚無模型",
    tone: "neutral",
  };

  return (
    <DisclosurePanel
      title={(
        <span className="flex min-w-0 flex-wrap items-center gap-2">
          <span className="min-w-0 break-all">{round.mode_id} · {round.round_id}</span>
          <StatusPill tone={status.tone}>{status.label}</StatusPill>
          <StatusPill tone={modelStatus.tone}>{modelStatus.label}</StatusPill>
        </span>
      )}
      description={`${round.view_count || 0} 張影像 · 展開查看影像與結果`}
      onToggle={(event) => {
        if (event.target === event.currentTarget) setOpen(event.currentTarget.open);
      }}
    >
      <InformationGrid
        items={[
          { label: "影像", value: `${round.view_count || 0} 張` },
          { label: "旋臂視角", value: `${round.rotating_view_count || 0} 張` },
          {
            label: "尖端標記信心",
            value: landmark?.valid
              ? formatNumberWithUnit(landmark.confidence * 100, "%")
              : "不可確認",
            tone: landmark?.valid ? "success" : "warning",
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
      {open ? (
        <AnalysisRunRoundImages
          analysisId={analysisId}
          round={round}
          model={model}
          hasLandmark={Boolean(landmark)}
        />
      ) : null}
    </DisclosurePanel>
  );
}

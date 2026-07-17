"use client";

import { useEffect, useState } from "react";
import {
  FiChevronLeft,
  FiChevronRight,
  FiCrosshair,
  FiPause,
  FiPlay,
  FiSkipForward,
} from "react-icons/fi";

import Button from "@/components/buttons/Button";
import { NumericInput } from "@/components/inputs/Input";
import InnerPanel from "@/components/panels/InnerPanel";
import { StatusPill } from "@/components/panels/Panel";
import SubsectionHeader from "@/components/headers/SubsectionHeader";

import {
  formatTipTimestamp,
  framePairStatusLabel,
} from "../lib/tipReviewUtils";

export default function TipReviewControls({
  activeCamera,
  currentFrameId,
  frame,
  frameIds,
  frameLoading,
  onActiveCameraChange,
  onFrameJump,
  onNext,
  onPlayingChange,
  onPrevious,
  playing,
}) {
  const [frameInput, setFrameInput] = useState(String(currentFrameId ?? ""));
  const currentIndex = frameIds.indexOf(currentFrameId);

  useEffect(() => {
    setFrameInput(String(currentFrameId ?? ""));
  }, [currentFrameId]);

  return (
    <InnerPanel>
      <SubsectionHeader
        title="影格控制"
        description="快捷鍵：←／→ 切換、Space 播放、T 俯視、S 側視、R 清除、X 無效、Enter 儲存並前進。"
      >
        <StatusPill tone={frameLoading ? "warning" : "neutral"}>
          {frameLoading ? "載入中" : `${currentIndex + 1} / ${frameIds.length}`}
        </StatusPill>
      </SubsectionHeader>

      <div className="grid gap-3 min-[720px]:grid-cols-[minmax(13rem,0.7fr)_minmax(0,1fr)_auto] min-[720px]:items-end">
        <div className="grid grid-cols-[minmax(0,1fr)_auto] items-end gap-2">
          <NumericInput
            id="tip-review-frame"
            label="指定影格"
            value={frameInput}
            min={frameIds[0] ?? 1}
            max={frameIds.at(-1) ?? 1}
            step={1}
            onValueChange={setFrameInput}
          />
          <Button onClick={() => onFrameJump(frameInput)}>
            <FiSkipForward
              className="size-4 shrink-0"
              aria-hidden="true"
            />
            前往
          </Button>
        </div>

        <div className="grid gap-1 text-xs font-semibold text-neutral-400">
          <span>影格：{currentFrameId ?? "—"}</span>
          <span>
            時間：{formatTipTimestamp(
              frame?.pair?.top_timestamp || frame?.pair?.side_timestamp,
            )}
          </span>
          <span>配對：{framePairStatusLabel(frame?.pair?.pair_status)}</span>
        </div>

        <div className="flex flex-wrap items-center justify-end gap-2">
          <Button
            disabled={currentIndex <= 0}
            onClick={onPrevious}
          >
            <FiChevronLeft
              className="size-4 shrink-0"
              aria-hidden="true"
            />
            前一影格
          </Button>
          <Button onClick={() => onPlayingChange(!playing)}>
            {playing ? (
              <FiPause
                className="size-4 shrink-0"
                aria-hidden="true"
              />
            ) : (
              <FiPlay
                className="size-4 shrink-0"
                aria-hidden="true"
              />
            )}
            {playing ? "暫停" : "播放"}
          </Button>
          <Button
            disabled={currentIndex < 0 || currentIndex >= frameIds.length - 1}
            onClick={onNext}
          >
            <FiChevronRight
              className="size-4 shrink-0"
              aria-hidden="true"
            />
            下一影格
          </Button>
        </div>
      </div>

      <div className="grid gap-2 min-[520px]:grid-cols-2">
        <Button
          className={activeCamera === "top"
            ? "border-emerald-200/60 bg-emerald-500/20 text-emerald-100 hover:border-emerald-100/80 hover:bg-emerald-400/25"
            : ""
          }
          aria-pressed={activeCamera === "top"}
          onClick={() => onActiveCameraChange("top")}
        >
          <FiCrosshair
            className="size-4 shrink-0"
            aria-hidden="true"
          />
          編輯俯視尖端（T）
        </Button>
        <Button
          className={activeCamera === "side"
            ? "border-emerald-200/60 bg-emerald-500/20 text-emerald-100 hover:border-emerald-100/80 hover:bg-emerald-400/25"
            : ""
          }
          aria-pressed={activeCamera === "side"}
          onClick={() => onActiveCameraChange("side")}
        >
          <FiCrosshair
            className="size-4 shrink-0"
            aria-hidden="true"
          />
          編輯側視尖端（S）
        </Button>
      </div>
    </InnerPanel>
  );
}

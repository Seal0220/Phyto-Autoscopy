import { useId } from "react";
import { FiPause, FiPlay, FiRotateCcw } from "react-icons/fi";
import Button from "@/components/buttons/Button";
import { NumericInput, SelectInput } from "@/components/inputs/Input";
import { ToggleRow } from "@/components/inputs/Toggle";

export default function FormalTrajectoryToolbar({
  display,
  onDisplayChange,
  transparency,
  onTransparencyChange,
  playback,
  disabled,
}) {
  const id = useId();
  return (
    <div className="grid min-w-0 gap-3">
      <div
        className="flex min-w-0 flex-wrap items-center gap-2"
        role="group"
        aria-label="三維軌跡顯示設定"
      >
        {[["lines", "軌跡（線）"], ["points", "點"], ["models", "模型"]].map(([key, label]) => (
          <ToggleRow
            key={key}
            label={label}
            checked={display[key]}
            disabled={disabled}
            className="min-w-30"
            onClick={() => onDisplayChange(key, !display[key])}
          />
        ))}
        {display.models ? (
          <>
            <label
              htmlFor={`${id}-transparency`}
              className="sr-only"
            >
              模型透明度
            </label>
            <NumericInput
              id={`${id}-transparency`}
              label="模型透明度"
              value={transparency}
              min={0}
              max={100}
              step={5}
              suffix="%"
              className="w-40"
              onValueChange={onTransparencyChange}
            />
          </>
        ) : null}
      </div>
      <div
        className="flex min-w-0 flex-wrap items-center gap-2"
        role="group"
        aria-label="三維軌跡播放控制"
      >
        <Button
          disabled={disabled}
          onClick={playback.togglePlayback}
          className="min-h-10 px-3 text-sm"
        >
          {playback.playing ? <FiPause aria-hidden="true" /> : <FiPlay aria-hidden="true" />}
          {playback.playing ? "暫停" : playback.cursor !== null && playback.cursor < playback.frames.length - 1 ? "繼續播放" : "播放"}
        </Button>
        <Button
          disabled={disabled}
          onClick={playback.restart}
          className="min-h-10 px-3 text-sm"
        >
          <FiRotateCcw aria-hidden="true" />
          從頭播放
        </Button>
        <Button
          disabled={disabled || playback.cursor === null}
          onClick={playback.showAll}
          className="min-h-10 px-3 text-sm"
        >
          顯示全部
        </Button>
        <label
          htmlFor={`${id}-speed`}
          className="sr-only"
        >
          播放速度
        </label>
        <SelectInput
          id={`${id}-speed`}
          label="播放速度"
          value={playback.speed}
          onValueChange={(value) => playback.setSpeed(Number(value))}
          options={[0.5, 1, 2, 4].map((value) => ({ value: String(value), label: `${value} 倍` }))}
          className="w-32"
        />
        <span className="min-w-0 text-xs font-semibold text-neutral-300">
          {playback.frame
            ? `${playback.cursor + 1} / ${playback.frames.length} · ${playback.frame.point.mode_id} · ${playback.frame.point.round_id}`
            : `全部 ${playback.frames.length} 點`}
        </span>
      </div>
    </div>
  );
}

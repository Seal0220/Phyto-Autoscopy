import {
  FiRefreshCw,
  FiRotateCcw,
} from "react-icons/fi";

import Button from "@/components/buttons/Button";
import SubsectionHeader from "@/components/headers/SubsectionHeader";
import { DurationInput, NumericInput } from "@/components/inputs/Input";
import { ToggleRow } from "@/components/inputs/Toggle";
import InnerPanel from "@/components/panels/InnerPanel";

import {
  SCHEDULE_CYCLE_DURATION_FIELD,
  SCHEDULE_CYCLE_INTERVAL_FIELD,
  SCHEDULE_COMMON_DEFAULTS,
  SCHEDULE_COMMON_FIELDS,
  SCHEDULE_DURATION_FIELD,
  SCHEDULE_TOTAL_CYCLES_FIELD,
} from "../scheduleConfig";
import { scheduleWithRotationEnabled } from "../lib/scheduleUtils";

export default function ScheduleCommonControls({
  schedule,
  setSchedule,
  defaultsLoading,
  defaultsLoadError,
  onLoadDefaults,
}) {
  const [durationKey, durationLabel, durationProps] = SCHEDULE_DURATION_FIELD;
  const [
    totalCyclesKey,
    totalCyclesLabel,
    totalCyclesProps,
  ] = SCHEDULE_TOTAL_CYCLES_FIELD;
  const [
    cycleDurationKey,
    cycleDurationLabel,
    cycleDurationProps,
  ] = SCHEDULE_CYCLE_DURATION_FIELD;
  const [
    cycleIntervalKey,
    cycleIntervalLabel,
    cycleIntervalProps,
  ] = SCHEDULE_CYCLE_INTERVAL_FIELD;
  const rotationEnabled = Boolean(schedule.rotation_enabled);

  function resetCommonControls() {
    setSchedule((previous) => ({
      ...previous,
      ...SCHEDULE_COMMON_DEFAULTS,
    }));
  }

  return (
    <section
      className="grid gap-5 py-1"
      aria-labelledby="shared-controls-title"
    >
      <SubsectionHeader
        titleId="shared-controls-title"
        title="通用配置"
        description="所有模式將共用相同控制配置。"
      >
        <div className="flex flex-wrap items-center justify-end gap-2">
          {defaultsLoadError || defaultsLoading ? (
            <Button
              disabled={defaultsLoading}
              onClick={() => void onLoadDefaults()}
            >
              <FiRefreshCw
                className="size-4 shrink-0"
                aria-hidden="true"
              />
              {defaultsLoading ? "載入中…" : "重新載入"}
            </Button>
          ) : null}
          <Button
            onClick={resetCommonControls}
          >
            <FiRotateCcw
              className="size-4 shrink-0"
              aria-hidden="true"
            />
            預設
          </Button>
        </div>
      </SubsectionHeader>
      <div className="flex flex-col gap-4 px-1">
        <ToggleRow
          checked={rotationEnabled}
          label="啟用旋臂"
          description="開啟後使用俯視角、側視角與旋臂視角進行多角度擷取；關閉後只使用俯視角與側視角進行時間間隔擷取。"
          className="w-40 min-w-40 max-w-40"
          onClick={() => setSchedule((previous) => (
            scheduleWithRotationEnabled(previous, !rotationEnabled)
          ))}
        />
        {rotationEnabled ? (
          <div className="grid min-w-0 grid-cols-[minmax(0,3fr)_minmax(0,2fr)] gap-4">
            <InnerPanel className="min-w-0 grid-cols-[auto_minmax(0,1fr)] items-center">
              <h3 className="m-0 shrink-0 text-sm font-black text-neutral-200">
                輪數時常
              </h3>
              <div className="grid min-w-0 grid-cols-[minmax(0,0.45fr)_minmax(0,1fr)_minmax(0,1fr)] gap-3">
                <NumericInput
                  id={`schedule-${totalCyclesKey}`}
                  label={totalCyclesLabel}
                  value={schedule[totalCyclesKey]}
                  onValueChange={(value) => setSchedule((previous) => ({
                    ...previous,
                    [totalCyclesKey]: value,
                  }))}
                  {...totalCyclesProps}
                  required
                  className="min-w-0"
                />
                <DurationInput
                  className="min-w-0"
                  id={`schedule-${cycleDurationKey}`}
                  label={cycleDurationLabel}
                  value={schedule[cycleDurationKey]}
                  onValueChange={(value) => setSchedule((previous) => ({
                    ...previous,
                    [cycleDurationKey]: value,
                  }))}
                  {...cycleDurationProps}
                  required
                />
                <DurationInput
                  className="min-w-0"
                  id={`schedule-${cycleIntervalKey}`}
                  label={cycleIntervalLabel}
                  value={schedule[cycleIntervalKey]}
                  onValueChange={(value) => setSchedule((previous) => ({
                    ...previous,
                    [cycleIntervalKey]: value,
                  }))}
                  {...cycleIntervalProps}
                  required
                />
              </div>
            </InnerPanel>
            <InnerPanel className="min-w-0 grid-cols-[auto_minmax(0,1fr)] items-center">
              <h3 className="m-0 shrink-0 text-sm font-black text-neutral-200">
                角度範圍
              </h3>
              <div className="grid min-w-0 grid-cols-3 gap-3">
                {SCHEDULE_COMMON_FIELDS.map(([key, label, props]) => (
                  <NumericInput
                    id={`schedule-${key}`}
                    key={key}
                    label={label}
                    value={schedule[key]}
                    onValueChange={(value) => setSchedule((previous) => ({
                      ...previous,
                      [key]: value,
                    }))}
                    {...props}
                    required
                    className="min-w-0"
                  />
                ))}
              </div>
            </InnerPanel>
          </div>
        ) : (
          <InnerPanel className="grid-cols-[auto_minmax(0,1fr)] items-center">
            <h3 className="m-0 shrink-0 text-sm font-black text-neutral-200">
              排程時長
            </h3>
            <DurationInput
              className="w-full min-w-0 justify-self-end"
              id={`schedule-${durationKey}`}
              label={durationLabel}
              value={schedule[durationKey]}
              onValueChange={(value) => setSchedule((previous) => ({
                ...previous,
                [durationKey]: value,
              }))}
              {...durationProps}
              required
            />
          </InnerPanel>
        )}
      </div>
    </section>
  );
}

import {
  FiRefreshCw,
  FiRotateCcw,
  FiSave,
} from "react-icons/fi";

import Button from "@/components/buttons/Button";
import SubsectionHeader from "@/components/headers/SubsectionHeader";
import { DurationInput, NumericInput } from "@/components/inputs/Input";
import { ToggleRow } from "@/components/inputs/Toggle";
import InnerPanel from "@/components/panels/InnerPanel";

import {
  SCHEDULE_ARM_HEIGHT_FIELD,
  SCHEDULE_CYCLE_INTERVAL_FIELD,
  SCHEDULE_COMMON_DEFAULTS,
  SCHEDULE_COMMON_FIELDS,
  SCHEDULE_DURATION_FIELD,
  SCHEDULE_STABILIZATION_FIELD,
  SCHEDULE_TOTAL_CYCLES_FIELD,
} from "../scheduleConfig";
import { scheduleWithRotationEnabled } from "../lib/scheduleUtils";

export default function ScheduleCommonControls({
  schedule,
  setSchedule,
  defaultsLoading,
  defaultsSaving,
  defaultsLoadError,
  onLoadDefaults,
  onSaveDefaults,
}) {
  const [durationKey, durationLabel, durationProps] = SCHEDULE_DURATION_FIELD;
  const [
    totalCyclesKey,
    totalCyclesLabel,
    totalCyclesProps,
  ] = SCHEDULE_TOTAL_CYCLES_FIELD;
  const [
    cycleIntervalKey,
    cycleIntervalLabel,
    cycleIntervalProps,
  ] = SCHEDULE_CYCLE_INTERVAL_FIELD;
  const [
    stabilizationKey,
    stabilizationLabel,
    stabilizationProps,
  ] = SCHEDULE_STABILIZATION_FIELD;
  const [
    armHeightKey,
    armHeightLabel,
    armHeightProps,
  ] = SCHEDULE_ARM_HEIGHT_FIELD;
  const rotationEnabled = Boolean(schedule.rotation_enabled);

  function resetCommonControls() {
    setSchedule((previous) => ({
      ...previous,
      ...SCHEDULE_COMMON_DEFAULTS,
      arm_height_mm: previous.arm_height_mm,
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
            variant="primary"
            disabled={defaultsLoading || defaultsSaving}
            onClick={() => void onSaveDefaults()}
          >
            <FiSave
              className="size-4 shrink-0"
              aria-hidden="true"
            />
            {defaultsSaving ? "儲存中…" : "儲存配置"}
          </Button>
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
          description="開啟後讓旋臂移動並以三鏡頭進行多角度擷取；關閉後旋臂保持固定，三個鏡頭仍會進行連續間隔擷取。"
          className="w-48 min-w-48 max-w-48"
          onClick={() => setSchedule((previous) => (
            scheduleWithRotationEnabled(previous, !rotationEnabled)
          ))}
        />
        {rotationEnabled ? (
          <>
            <div className="flex flex-col min-w-0 gap-4">
              <InnerPanel className="min-w-0 grid-cols-[auto_minmax(0,1fr)] items-center">
                <h3 className="m-0 mr-1 shrink-0 text-sm font-black text-neutral-200">
                  輪次設定
                </h3>
                <div className="flex flex-row min-w-0 gap-3">
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
                    className="min-w-0 w-30"
                  />
                  <DurationInput
                    className="min-w-0 w-108"
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
                <h3 className="m-0 mr-1 shrink-0 text-sm font-black text-neutral-200">
                  角度範圍
                </h3>
                <div className="flex flex-row min-w-0 gap-3">
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
                      className="min-w-0 w-30"
                    />
                  ))}
                </div>
              </InnerPanel>
            </div>
            <InnerPanel className="min-w-0 grid-cols-[auto_minmax(0,1fr)] items-center">
              <h3 className="m-0 mr-1 shrink-0 text-sm font-black text-neutral-200">
                執行行為
              </h3>
              <div className="flex flex-row min-w-0 gap-3">
                <NumericInput
                  id={`schedule-${armHeightKey}`}
                  label={armHeightLabel}
                  value={schedule[armHeightKey]}
                  onValueChange={(value) => setSchedule((previous) => ({
                    ...previous,
                    [armHeightKey]: value,
                  }))}
                  {...armHeightProps}
                  className="min-w-0 w-40"
                />
                <DurationInput
                  id={`schedule-${stabilizationKey}`}
                  label={stabilizationLabel}
                  value={schedule[stabilizationKey]}
                  onValueChange={(value) => setSchedule((previous) => ({
                    ...previous,
                    [stabilizationKey]: value,
                  }))}
                  {...stabilizationProps}
                  required
                  className="min-w-0 w-108"
                />
                <ToggleRow
                  checked={Boolean(schedule.capture_on_return)}
                  label="往返皆擷取"
                  description="關閉時抵達終點後直接回到原點；開啟時依正向相同配置在回程擷取。"
                  className="min-w-48 w-48"
                  onClick={() => setSchedule((previous) => ({
                    ...previous,
                    capture_on_return: !previous.capture_on_return,
                  }))}
                />
                <ToggleRow
                  checked={Boolean(schedule.return_to_origin)}
                  label="結束後回到原點"
                  description="排程完成、停止或失敗後讓旋臂回到原點。"
                  className="min-w-48 w-48"
                  onClick={() => setSchedule((previous) => ({
                    ...previous,
                    return_to_origin: !previous.return_to_origin,
                  }))}
                />
              </div>
            </InnerPanel>
          </>
        ) : (
          <InnerPanel className="grid-cols-[auto_minmax(0,1fr)] items-center">
            <h3 className="m-0 mr-1 shrink-0 text-sm font-black text-neutral-200">
              排程時長
            </h3>
            <DurationInput
              className="min-w-0 w-108"
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

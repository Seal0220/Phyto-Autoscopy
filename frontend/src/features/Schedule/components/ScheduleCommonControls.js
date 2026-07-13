import { FiRotateCcw } from "react-icons/fi";

import Button from "@/components/buttons/Button";
import SubsectionHeader from "@/components/headers/SubsectionHeader";
import { DurationInput, NumericInput } from "@/components/inputs/Input";

import {
  SCHEDULE_COMMON_DEFAULTS,
  SCHEDULE_COMMON_FIELDS,
  SCHEDULE_DURATION_FIELD,
} from "../scheduleConfig";

export default function ScheduleCommonControls({
  schedule,
  setSchedule,
}) {
  const [durationKey, durationLabel, durationProps] = SCHEDULE_DURATION_FIELD;

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
        <Button
          onClick={resetCommonControls}
        >
          <FiRotateCcw
            className="size-4"
            aria-hidden="true"
          />
          預設
        </Button>
      </SubsectionHeader>
      <div className="grid gap-3 px-1 min-[520px]:grid-cols-2 min-[1180px]:grid-cols-6">
        <DurationInput
          className="min-[520px]:col-span-2"
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
          />
        ))}
      </div>
    </section>
  );
}

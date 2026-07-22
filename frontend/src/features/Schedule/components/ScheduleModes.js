import { FiPlus } from "react-icons/fi";

import Button from "@/components/buttons/Button";
import SubsectionHeader from "@/components/headers/SubsectionHeader";

import {
  SCHEDULE_MODE_META,
} from "../scheduleConfig";
import { scheduleModeTypeFromLabel } from "../lib/scheduleUtils";
import ScheduleModeCard from "./ScheduleModeCard";

export default function ScheduleModes({
  schedule,
  setSchedule,
  canEdit,
  rotationEnabled,
}) {
  function addMode() {
    let index = schedule.modes.length + 1;

    while (schedule.modes.some((mode) => mode.id === `mode-${index}`)) {
      index += 1;
    }

    setSchedule((previous) => ({
      ...previous,
      modes: [
        ...previous.modes,
        {
          id: `mode-${index}`,
          type: rotationEnabled
            ? "time_interval"
            : "continuous_interval",
          ...SCHEDULE_MODE_META[
            rotationEnabled
              ? "time_interval"
              : "continuous_interval"
          ].initial,
        },
      ],
    }));
  }

  function updateMode(
    modeId,
    patch,
  ) {
    setSchedule((previous) => ({
      ...previous,
      modes: previous.modes.map((mode) => (
        mode.id === modeId
          ? { ...mode, ...patch }
          : mode
      )),
    }));
  }

  function changeModeType(
    modeId,
    label,
  ) {
    const type = scheduleModeTypeFromLabel(label);

    setSchedule((previous) => ({
      ...previous,
      modes: previous.modes.map((mode) => (
        mode.id === modeId
          ? {
            id: mode.id,
            type,
            ...SCHEDULE_MODE_META[type].initial,
          }
          : mode
      )),
    }));
  }

  function removeMode(modeId) {
    setSchedule((previous) => ({
      ...previous,
      modes: previous.modes.filter((mode) => mode.id !== modeId),
    }));
  }

  return (
    <section
      className="grid gap-3"
      aria-labelledby="capture-modes-title"
    >
      <SubsectionHeader
        className="mb-3"
        titleId="capture-modes-title"
        title="擷取模式"
        description={rotationEnabled
          ? "共五種擷取模式，每一模式將獨立產生紀錄檔。"
          : "未啟用旋臂時固定使用雙鏡頭連續間隔擷取。"
        }
      >
        <Button
          onClick={addMode}
          disabled={!canEdit || schedule.modes.length >= 20}
        >
          <FiPlus
            className="size-4"
            aria-hidden="true"
          />
          新增擷取
        </Button>
      </SubsectionHeader>

      {schedule.modes.length ? (
        <div className="grid grid-cols-3 gap-3">
          {schedule.modes.map((mode, index) => (
            <ScheduleModeCard
              key={mode.id}
              mode={mode}
              index={index}
              canEdit={canEdit}
              fixedContinuousInterval={!rotationEnabled}
              onChangeType={(label) => changeModeType(mode.id, label)}
              onRemove={() => removeMode(mode.id)}
              onUpdate={(patch) => updateMode(mode.id, patch)}
            />
          ))}
        </div>
      ) : (
        <div className="grid min-h-28 place-items-center rounded-2xl border border-dashed border-white/15 bg-black/15 px-4 text-center text-sm font-semibold text-neutral-500">
          尚未加入擷取模式，請至少新增一個模式後再開始排程。
        </div>
      )}
    </section>
  );
}

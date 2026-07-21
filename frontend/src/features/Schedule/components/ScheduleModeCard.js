import { FiTrash2 } from "react-icons/fi";

import Button from "@/components/buttons/Button";
import SubsectionHeader from "@/components/headers/SubsectionHeader";
import { SelectInput } from "@/components/inputs/Input";
import InnerPanel from "@/components/panels/InnerPanel";

import {
  SCHEDULE_MODE_LABELS,
  SCHEDULE_MODE_META,
} from "../scheduleConfig";
import ScheduleModeFields from "./ScheduleModeFields";

export default function ScheduleModeCard({
  mode,
  index,
  canEdit,
  fixedTimeInterval,
  onChangeType,
  onRemove,
  onUpdate,
}) {
  const selectedMeta = SCHEDULE_MODE_META[mode.type] || SCHEDULE_MODE_META.time_interval;

  return (
    <InnerPanel className="flex content-start gap-3">
      <SubsectionHeader
        className="mb-2"
        title={`擷取 ${String(index + 1).padStart(2, "0")}`}
        titleMode={1}
      >
        <Button
          className="size-10 min-h-10 shrink-0 p-0!"
          variant="dangerGhost"
          aria-label={`移除${selectedMeta.label}`}
          onClick={onRemove}
          disabled={!canEdit}
        >
          <FiTrash2
            className="size-5 shrink-0"
            aria-hidden="true"
          />
        </Button>
      </SubsectionHeader>
      <div className="mt-auto grid grid-rows-2 gap-3">
        <SelectInput
          id={`schedule-${mode.id}-type`}
          label="擷取模式"
          value={selectedMeta.label}
          options={fixedTimeInterval
            ? [SCHEDULE_MODE_META.time_interval.label]
            : SCHEDULE_MODE_LABELS
          }
          description={selectedMeta.description}
          onValueChange={onChangeType}
        />
        <ScheduleModeFields
          mode={mode}
          onUpdate={onUpdate}
        />
      </div>
    </InnerPanel>
  );
}

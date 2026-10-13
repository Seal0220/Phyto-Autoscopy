import {
  FiChevronLeft,
  FiChevronRight,
} from "react-icons/fi";

import Button from "@/components/buttons/Button";
import { SelectInput } from "@/components/inputs/Input";

import { ANALYSIS_IMAGE_SPACE_OPTIONS } from "../analysisRunConfig";

export default function AnalysisRunRoundImageControls({
  roundKey,
  groups,
  selectedIndex,
  onGroupChange,
  space,
  onSpaceChange,
  marking,
  compact = false,
}) {
  return (
    <div className={`grid min-w-0 gap-2
      ${compact
        ? "min-w-[26rem] grid-cols-[minmax(8rem,1fr)_minmax(8rem,1fr)_auto]"
        : "@min-[720px]:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto]"
      }`}
    >
      <SelectInput
        id={`analysis-snapshot-${roundKey}`}
        label="擷取組"
        value={String(selectedIndex)}
        options={groups.map((item, index) => ({ value: String(index), label: item.key }))}
        onValueChange={(value) => onGroupChange(Number(value))}
      />
      {!marking ? (
        <SelectInput
          id={`analysis-image-space-${roundKey}`}
          label="影像類型"
          value={space}
          options={ANALYSIS_IMAGE_SPACE_OPTIONS}
          onValueChange={onSpaceChange}
        />
      ) : null}
      <div className={`flex items-end justify-end gap-2 ${marking && compact ? "col-span-2" : ""}`}>
        <Button
          className="px-3!"
          aria-label="上一組擷取影像"
          disabled={selectedIndex === 0}
          onClick={() => onGroupChange(selectedIndex - 1)}
        >
          <FiChevronLeft aria-hidden="true" />
        </Button>
        <span className="self-center whitespace-nowrap text-xs font-semibold text-neutral-400">
          {selectedIndex + 1} / {groups.length}
        </span>
        <Button
          className="px-3!"
          aria-label="下一組擷取影像"
          disabled={selectedIndex === groups.length - 1}
          onClick={() => onGroupChange(selectedIndex + 1)}
        >
          <FiChevronRight aria-hidden="true" />
        </Button>
      </div>
    </div>
  );
}

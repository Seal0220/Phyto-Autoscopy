import {
  FiCheck,
  FiCircle,
} from "react-icons/fi";

import SubsectionHeader from "@/components/headers/SubsectionHeader";
import InnerPanel from "@/components/panels/InnerPanel";

import {
  analysisModeConfigurationLabel,
  analysisModePillLabel,
} from "../lib/analysisUtils";

export default function AnalysisModeSelector({
  modes,
  selectedModeIds,
  onSelectionChange,
}) {
  return (
    <InnerPanel
      mode="dark"
      aria-labelledby="analysis-mode-selector-title"
    >
      <SubsectionHeader
        titleId="analysis-mode-selector-title"
        title="選取模式"
        description="可複選多個擷取模式。"
      />

      <div
        className="flex min-w-0 flex-wrap gap-2"
        aria-label="選取要分析的擷取模式"
        role="group"
      >
        {modes.map((mode) => {
          const selected = selectedModeIds.includes(mode.id);
          const ModeIcon = selected ? FiCheck : FiCircle;
          const configurationLabel = analysisModeConfigurationLabel(mode);

          return (
            <button
              className={`inline-flex min-h-10 max-w-full cursor-pointer flex-wrap items-center justify-center gap-x-2 gap-y-1 rounded-full border pl-3 pr-4 py-1.5 text-xs font-black transition-[background-color,border-color,color,opacity] duration-150 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-300 motion-reduce:transition-none 
                ${selected
                  ? "border-emerald-200/75 bg-emerald-500/20 text-emerald-100 hover:border-emerald-100 hover:bg-emerald-400/25"
                  : "border-white/15 bg-black/20 text-neutral-300 hover:border-white/25 hover:bg-white/10 hover:text-neutral-100"
                }`}
              aria-label={`${analysisModePillLabel(mode)}，${configurationLabel}，${mode.image_count} 張，${selected ? "已選取" : "未選取"}`}
              aria-pressed={selected}
              key={mode.id}
              onClick={() => void onSelectionChange(mode.id)}
              type="button"
            >
              <ModeIcon
                className="size-3.5 shrink-0"
                aria-hidden="true"
              />
              <span className="min-w-0">
                {analysisModePillLabel(mode)}
              </span>
              <span
                className="text-neutral-500"
                aria-hidden="true"
              >
                ·
              </span>
              <span className={selected ? "text-emerald-200" : "text-neutral-400"}>
                {configurationLabel}
              </span>
              <span
                className="text-neutral-500"
                aria-hidden="true"
              >
                ·
              </span>
              <span className={selected ? "text-emerald-200" : "text-neutral-400"}>
                {mode.image_count} 張
              </span>
            </button>
          );
        })}
      </div>
    </InnerPanel>
  );
}

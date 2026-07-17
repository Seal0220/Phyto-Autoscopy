import InnerPanel from "@/components/panels/InnerPanel";
import SubsectionHeader from "@/components/headers/SubsectionHeader";
import { NumericInput } from "@/components/inputs/Input";

const ROI_FIELDS = [
  {
    key: "x",
    label: "X",
    min: 0,
  },
  {
    key: "y",
    label: "Y",
    min: 0,
  },
  {
    key: "width",
    label: "寬度",
    min: 1,
  },
  {
    key: "height",
    label: "高度",
    min: 1,
  },
];

function AnalysisSetupRoiFields({
  camera,
  label,
  roi,
  onChange,
}) {
  return (
    <InnerPanel>
      <SubsectionHeader
        title={`${label} ROI`}
        description="ROI 位置不可為負值，寬度與高度必須大於零。"
        titleMode={1}
      />
      <div className="grid gap-3 min-[520px]:grid-cols-2 min-[900px]:grid-cols-4">
        {ROI_FIELDS.map((field) => (
          <NumericInput
            id={`analysis-${camera}-roi-${field.key}`}
            key={field.key}
            label={`${label} ROI ${field.label}`}
            value={roi[field.key]}
            onValueChange={(value) => onChange(
              camera,
              field.key,
              value,
            )}
            min={field.min}
            step={1}
            suffix="px"
            required
          />
        ))}
      </div>
    </InnerPanel>
  );
}

export default function AnalysisSetupRangeStep({
  setup,
  onChange,
  onRoiChange,
}) {
  return (
    <section
      className="grid gap-4"
      aria-labelledby="analysis-range-step-title"
    >
      <SubsectionHeader
        titleId="analysis-range-step-title"
        title="設定分析範圍"
        description="影格範圍以一為起始索引；人工影格偏移可使用正數或負數校正時間不同步。"
      />

      <div className="grid gap-3 min-[520px]:grid-cols-3">
        <NumericInput
          id="analysis-start-frame"
          label="起始影格"
          value={setup.startFrame}
          onValueChange={(value) => onChange("startFrame", value)}
          min={1}
          step={1}
          suffix="影格"
          required
        />
        <NumericInput
          id="analysis-end-frame"
          label="結束影格"
          value={setup.endFrame}
          onValueChange={(value) => onChange("endFrame", value)}
          min={1}
          step={1}
          suffix="影格"
          required
        />
        <NumericInput
          id="analysis-manual-frame-offset"
          label="人工影格偏移"
          value={setup.manualFrameOffset}
          onValueChange={(value) => onChange("manualFrameOffset", value)}
          step={1}
          suffix="影格"
          description="時間同步不正確時調整側視影格配對；未偏移時保持為 0。"
          required
        />
      </div>

      <AnalysisSetupRoiFields
        camera="top"
        label="俯視"
        roi={setup.topRoi}
        onChange={onRoiChange}
      />
      <AnalysisSetupRoiFields
        camera="side"
        label="側視"
        roi={setup.sideRoi}
        onChange={onRoiChange}
      />
    </section>
  );
}

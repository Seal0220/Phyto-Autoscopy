import {
  DurationInput,
  NumericInput,
  TextInput,
} from "@/components/inputs/Input";

export default function ModeFields({
  mode,
  onUpdate,
}) {
  const fieldId = `schedule-${mode.id}-value`;

  if (mode.type === "seconds_interval") {
    return (
      <DurationInput
        id={fieldId}
        label="擷取間隔"
        value={mode.interval_seconds}
        onValueChange={(value) => onUpdate({ interval_seconds: value })}
        unit="seconds"
        required
      />
    );
  }

  if (mode.type === "angle_interval") {
    return (
      <NumericInput
        id={fieldId}
        label="角度間隔"
        value={mode.interval_degrees}
        onValueChange={(value) => onUpdate({ interval_degrees: value })}
        min={0.1}
        max={360}
        step={0.1}
        suffix="度"
        required
      />
    );
  }

  if (mode.type === "specific_angles") {
    return (
      <TextInput
        id={fieldId}
        label="角度字串"
        value={mode.angles}
        onValueChange={(value) => onUpdate({ angles: value })}
        placeholder="30,45,60,122"
        required
      />
    );
  }

  return (
    <NumericInput
      id={fieldId}
      label="擷取點數（含頭尾）"
      value={mode.points}
      onValueChange={(value) => onUpdate({ points: value })}
      min={2}
      max={10000}
      step={1}
      suffix="點"
      required
    />
  );
}

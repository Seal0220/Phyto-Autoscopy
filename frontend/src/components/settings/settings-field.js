import { DurationInput, NumericInput, SelectInput, TextInput } from "@/components/ui/input";
import ToggleRow from "@/components/ui/toggle-row";
import { fieldMeta } from "@/lib/settings";

function fieldId(group, path) {
  return `setting-${group}-${path.join("-")}`;
}

function BooleanSettingsField({ leaf, onChange }) {
  const meta = fieldMeta(leaf);
  const enabled = Boolean(leaf.value);
  return <ToggleRow checked={enabled} label={meta.label} description={meta.description} onClick={() => onChange(leaf.path, !enabled)} />;
}

function StandardSettingsField({ group, leaf, onChange }) {
  const meta = fieldMeta(leaf);
  const id = fieldId(group, leaf.path);
  const value = leaf.value ?? "";
  const update = (nextValue) => onChange(leaf.path, nextValue);
  if (meta.type === "select") return <SelectInput id={id} label={meta.label} value={value} onValueChange={update} options={meta.options} description={meta.description} />;
  if (meta.type === "duration") return <DurationInput id={id} label={meta.label} value={value} onValueChange={update} unit={meta.unit} description={meta.description} />;
  if (meta.type === "number") return <NumericInput id={id} label={meta.label} value={value} onValueChange={update} min={meta.min} max={meta.max} step={meta.step} suffix={meta.suffix} description={meta.description} />;
  return <TextInput id={id} label={meta.label} value={value} onValueChange={update} description={meta.description} />;
}

export default function SettingsField({ group, leaf, onChange }) {
  return typeof leaf.value === "boolean" ? (
    <BooleanSettingsField leaf={leaf} onChange={onChange} />
  ) : (
    <StandardSettingsField group={group} leaf={leaf} onChange={onChange} />
  );
}

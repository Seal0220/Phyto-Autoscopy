import { NumericInput } from "@/components/inputs/Input";
import { ToggleRow } from "@/components/inputs/Toggle";
import { imagePreviewFieldMeta } from "@/features/ImagePreview/lib/imagePreviewUtils";

function fieldId(path) {
  return `image-preview-setting-${path.join("-")}`;
}

export default function ImagePreviewField({
  leaf,
  onChange,
}) {
  const meta = imagePreviewFieldMeta(leaf);

  if (typeof leaf.value === "boolean") {
    const checked = Boolean(leaf.value);

    return (
      <ToggleRow
        checked={checked}
        label={meta.label}
        description={meta.description}
        onClick={() => onChange(leaf.path, !checked)}
      />
    );
  }

  return (
    <NumericInput
      id={fieldId(leaf.path)}
      label={meta.label}
      value={leaf.value ?? ""}
      onValueChange={(value) => onChange(leaf.path, value)}
      min={meta.min}
      max={meta.max}
      step={meta.step}
      suffix={meta.suffix}
      description={meta.description}
    />
  );
}

import {
  IMAGE_PREVIEW_FIELD_META,
  IMAGE_PREVIEW_ORDER,
  IMAGE_PREVIEW_SETTINGS_CONFIG,
} from "@/features/ImagePreview/imagePreviewConfig";

function isPlainObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function cloneValue(value) {
  if (typeof structuredClone === "function") {
    return structuredClone(value);
  }

  return JSON.parse(JSON.stringify(value));
}

function collectImagePreviewLeaves(
  value,
  rule,
  path,
  leaves,
) {
  if (rule === true && !isPlainObject(value)) {
    leaves.push({ path, value });
    return leaves;
  }

  if (!isPlainObject(value) || !isPlainObject(rule)) {
    return leaves;
  }

  for (const [key, childRule] of Object.entries(rule)) {
    if (Object.hasOwn(value, key)) {
      collectImagePreviewLeaves(
        value[key],
        childRule,
        [...path, key],
        leaves,
      );
    }
  }

  return leaves;
}

function setNestedValue(
  target,
  path,
  value,
) {
  let current = target;

  path.forEach((key, index) => {
    if (index === path.length - 1) {
      current[key] = value;
      return;
    }

    if (!isPlainObject(current[key])) {
      current[key] = {};
    }

    current = current[key];
  });
}

export function imagePreviewSettingsSections(payload) {
  return IMAGE_PREVIEW_ORDER.map((imagePreviewId) => ({
    imagePreviewId,
    leaves: collectImagePreviewLeaves(
      payload?.cameras?.[imagePreviewId],
      IMAGE_PREVIEW_SETTINGS_CONFIG.cameras[imagePreviewId],
      ["cameras", imagePreviewId],
      [],
    ),
  })).filter(({ leaves }) => leaves.length > 0);
}

export function imagePreviewFieldMeta(leaf) {
  const key = leaf.path.at(-1);
  return IMAGE_PREVIEW_FIELD_META[key] || {
    label: key.replaceAll("_", " "),
  };
}

export function visibleImagePreviewSettings(payload) {
  return imagePreviewSettingsSections(payload).flatMap(({ leaves }) => leaves);
}

export function serializeImagePreviewSettingsPayload(payload) {
  const nextPayload = cloneValue(payload);

  for (const leaf of visibleImagePreviewSettings(nextPayload)) {
    const meta = imagePreviewFieldMeta(leaf);

    if (meta.type !== "number") {
      continue;
    }

    const value = Number(leaf.value);

    if (!Number.isFinite(value)) {
      throw new Error(`${meta.label} 必須是有效數字。`);
    }

    if (meta.min !== undefined && value < meta.min) {
      throw new Error(`${meta.label} 不可小於 ${meta.min}。`);
    }

    if (meta.max !== undefined && value > meta.max) {
      throw new Error(`${meta.label} 不可大於 ${meta.max}。`);
    }

    setNestedValue(nextPayload, leaf.path, value);
  }

  return nextPayload;
}

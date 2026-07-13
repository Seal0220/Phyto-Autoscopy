import {
  FIELD_META,
  SECTION_META,
  SECTION_ORDER,
  SETTINGS_CONFIG,
} from "../settingsConfig";

export function cloneValue(value) {
  if (typeof structuredClone === "function") {
    return structuredClone(value);
  }

  return JSON.parse(JSON.stringify(value));
}

function isPlainObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function collectVisibleLeaves(
  value,
  rule,
  path = [],
  leaves = [],
) {
  if (rule === true && !isPlainObject(value)) {
    leaves.push({
      path,
      value,
    });
    return leaves;
  }

  if (!isPlainObject(value) || !isPlainObject(rule)) {
    return leaves;
  }

  for (const [key, childRule] of Object.entries(rule)) {
    if (Object.hasOwn(value, key)) {
      collectVisibleLeaves(
        value[key],
        childRule,
        [...path, key],
        leaves,
      );
    }
  }

  return leaves;
}

export function visibleSettings(
  group,
  payload,
) {
  return collectVisibleLeaves(payload, SETTINGS_CONFIG[group]);
}

export function fieldMeta(leaf) {
  const key = leaf.path.at(-1);
  return FIELD_META[key] || {
    label: key.replaceAll("_", " "),
  };
}

export function setNestedValue(
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

function sectionFor(
  group,
  path,
) {
  const key = path.at(-1);

  if (group === "motor") {
    return "movement";
  }

  if (group === "experiment") {
    return ["capture_top", "capture_fixed_side", "capture_rotating_arm"].includes(key)
      ? "capture"
      : "execution";
  }

  return "root";
}

export function groupedVisibleSettings(
  group,
  payload,
) {
  const grouped = new Map();

  for (const leaf of visibleSettings(group, payload)) {
    const section = sectionFor(group, leaf.path);
    const current = grouped.get(section) || [];
    current.push(leaf);
    grouped.set(section, current);
  }

  return SECTION_ORDER[group]
    .map((section) => ({
      section,
      leaves: grouped.get(section) || [],
    }))
    .filter(({ leaves }) => leaves.length > 0);
}

export function sectionMeta(
  group,
  section,
) {
  return SECTION_META[group]?.[section] || {
    title: section.replaceAll("_", " "),
  };
}

export function serializeSettingsPayload(
  group,
  payload,
) {
  const next = cloneValue(payload);

  for (const leaf of visibleSettings(group, next)) {
    const meta = fieldMeta(leaf);

    if (!["number", "duration"].includes(meta.type)) {
      continue;
    }

    const number = Number(leaf.value);

    if (!Number.isFinite(number)) {
      throw new Error(`${meta.label} 必須是有效數字。`);
    }

    if (meta.min !== undefined && number < meta.min) {
      throw new Error(`${meta.label} 不可小於 ${meta.min}。`);
    }

    if (meta.max !== undefined && number > meta.max) {
      throw new Error(`${meta.label} 不可大於 ${meta.max}。`);
    }

    setNestedValue(next, leaf.path, number);
  }

  return next;
}

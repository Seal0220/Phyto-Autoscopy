import {
  IMAGE_PREVIEW_FIELD_META,
  IMAGE_PREVIEW_META,
  IMAGE_PREVIEW_ORDER,
  IMAGE_PREVIEW_SETTINGS_CONFIG,
} from "../imagePreviewConfig.js";

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

export function formatImagePreviewFps(value) {
  const fps = Number(value);

  if (!Number.isFinite(fps) || fps <= 0) return "0";
  return String(Math.round(fps));
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

export function imagePreviewDeviceOptions(
  scanResults,
  imagePreviewId,
  cameraDrafts = {},
) {
  const devicesByIndex = new Map();
  const draftAssignments = new Map();
  const hasCameraDrafts = Object.keys(cameraDrafts).length > 0;

  for (const [cameraId, config] of Object.entries(cameraDrafts)) {
    const deviceIndex = Number(config?.device_index);

    if (
      config?.enabled
      && Number.isInteger(deviceIndex)
      && deviceIndex >= 0
      && deviceIndex <= 63
    ) {
      draftAssignments.set(deviceIndex, cameraId);
    }
  }

  for (const result of Array.isArray(scanResults) ? scanResults : []) {
    const deviceIndex = Number(result?.device_index);

    if (
      !result?.connected
      || !Number.isInteger(deviceIndex)
      || deviceIndex < 0
      || deviceIndex > 63
    ) {
      continue;
    }

    devicesByIndex.set(deviceIndex, {
      assignedCameraId: typeof result?.camera_id === "string" ? result.camera_id : null,
      deviceName: typeof result?.device_name === "string" ? result.device_name.trim() : "",
    });
  }

  const availableOptions = [...devicesByIndex.entries()]
    .sort(([left], [right]) => left - right)
    .flatMap(([deviceIndex, state]) => {
      const draftAssignment = draftAssignments.get(deviceIndex);
      const assignedCameraId = draftAssignment || (!hasCameraDrafts ? state.assignedCameraId : null);
      const usedByAnotherCamera = assignedCameraId && assignedCameraId !== imagePreviewId;

      if (usedByAnotherCamera) return [];

      const deviceName = state.deviceName || "未知裝置";

      return [{
        value: String(deviceIndex),
        label: `[${deviceIndex}] ${deviceName}`,
      }];
    });

  return [
    {
      value: "",
      label: "無",
    },
    ...availableOptions,
  ];
}

export function unavailableImagePreviewAssignments(
  payload,
  scanResults,
) {
  const availableIndexes = new Set(
    (Array.isArray(scanResults) ? scanResults : [])
      .filter((result) => result?.connected)
      .map((result) => Number(result?.device_index))
      .filter((deviceIndex) => (
        Number.isInteger(deviceIndex)
        && deviceIndex >= 0
        && deviceIndex <= 63
      )),
  );

  return IMAGE_PREVIEW_ORDER.filter((imagePreviewId) => {
    const deviceIndex = payload?.cameras?.[imagePreviewId]?.device_index;

    if (deviceIndex === null || deviceIndex === undefined || deviceIndex === "") {
      return false;
    }

    return !availableIndexes.has(Number(deviceIndex));
  });
}

export function visibleImagePreviewSettings(payload) {
  return imagePreviewSettingsSections(payload).flatMap(({ leaves }) => leaves);
}

export function serializeImagePreviewSettingsPayload(payload) {
  const nextPayload = cloneValue(payload);

  for (const leaf of visibleImagePreviewSettings(nextPayload)) {
    const meta = imagePreviewFieldMeta(leaf);

    if (meta.type !== "number" && meta.valueType !== "number") {
      continue;
    }

    if (
      meta.type === "select"
      && (
        leaf.value === null
        || leaf.value === undefined
        || String(leaf.value).trim() === ""
      )
    ) {
      setNestedValue(nextPayload, leaf.path, null);
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

  const assignedIndexes = new Map();

  for (const imagePreviewId of IMAGE_PREVIEW_ORDER) {
    const config = nextPayload?.cameras?.[imagePreviewId];

    if (!config?.enabled) continue;

    if (config.device_index === null || config.device_index === undefined) {
      const cameraLabel = IMAGE_PREVIEW_META[imagePreviewId]?.label || imagePreviewId;
      throw new Error(`${cameraLabel}已啟用，請先選擇裝置。`);
    }

    const deviceIndex = Number(config.device_index);
    const previousId = assignedIndexes.get(deviceIndex);

    if (previousId) {
      const previousLabel = IMAGE_PREVIEW_META[previousId]?.label || previousId;
      const currentLabel = IMAGE_PREVIEW_META[imagePreviewId]?.label || imagePreviewId;
      throw new Error(
        `裝置 ${deviceIndex} 不可同時指派給${previousLabel}與${currentLabel}。`,
      );
    }

    assignedIndexes.set(deviceIndex, imagePreviewId);
  }

  return nextPayload;
}

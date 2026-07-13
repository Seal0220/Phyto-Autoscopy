import {
  RECORD_EXPORT_META,
  RECORD_STATUS_LABELS,
  STORAGE_PATH_FIELDS,
} from "../storageConfig";

function cloneValue(value) {
  if (typeof structuredClone === "function") {
    return structuredClone(value);
  }

  return JSON.parse(JSON.stringify(value));
}

export function serializeStoragePayload(payload) {
  if (!payload || typeof payload !== "object" || !payload.paths || typeof payload.paths !== "object") {
    throw new Error("儲存位置設定格式無效。");
  }

  const nextPayload = cloneValue(payload);

  if (
    !nextPayload.paths.captures_dir
    && nextPayload.paths.records_dir
  ) {
    nextPayload.paths.captures_dir = nextPayload.paths.records_dir;
  }

  delete nextPayload.paths.records_dir;

  for (const field of STORAGE_PATH_FIELDS) {
    const value = String(nextPayload.paths[field.key] ?? "").trim();

    if (!value) {
      throw new Error(`${field.label}不可為空白。`);
    }

    nextPayload.paths[field.key] = value;
  }

  return nextPayload;
}

export function recordStatusLabel(status) {
  return RECORD_STATUS_LABELS[status] || "未知狀態";
}

export function recordExportMeta(format) {
  const meta = RECORD_EXPORT_META[format];

  if (!meta) {
    throw new Error("不支援的紀錄匯出格式。");
  }

  return meta;
}

export function recordExportFilename(
  recordId,
  filenameSuffix,
) {
  const safeRecordId = String(recordId || "record")
    .replace(/[^a-zA-Z0-9._-]/g, "_")
    .slice(0, 120) || "record";

  return `${safeRecordId}-${filenameSuffix}`;
}

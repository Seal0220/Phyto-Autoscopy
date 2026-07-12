import { STORAGE_PATH_FIELDS } from "../storageConfig";

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

  for (const field of STORAGE_PATH_FIELDS) {
    const value = String(nextPayload.paths[field.key] ?? "").trim();

    if (!value) {
      throw new Error(`${field.label}不可為空白。`);
    }

    nextPayload.paths[field.key] = value;
  }

  return nextPayload;
}

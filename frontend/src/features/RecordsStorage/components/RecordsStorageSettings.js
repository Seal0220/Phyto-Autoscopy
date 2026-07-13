"use client";

import { FiSave } from "react-icons/fi";

import Button from "@/components/buttons/Button";
import { TextInput } from "@/components/inputs/Input";
import SettingPanel from "@/components/panels/SettingPanel";
import useSettings from "@/hooks/useSettings";

import { STORAGE_PATH_FIELDS } from "../storageConfig";
import { serializeStoragePayload } from "../lib/storageUtils";

export default function RecordsStorageSettings({
  onNotify,
  open,
  locked,
}) {
  const {
    payload,
    loading,
    saving,
    loadFailed,
    updateField,
    saveGroup,
  } = useSettings({
    group: "default",
    onNotify,
    open,
    serializePayload: serializeStoragePayload,
  });
  const paths = payload?.paths || {};

  return (
    <SettingPanel
      label="儲存"
      open={open}
      locked={locked}
      footer={(
        <Button
          variant="primary"
          onClick={() => void saveGroup()}
          disabled={!payload || saving || loading}
        >
          <FiSave
            className="size-4 shrink-0"
            aria-hidden="true"
          />
          {saving ? "儲存中…" : "儲存路徑設定"}
        </Button>
      )}
    >
      {loading && !payload ? (
        <p className="grid min-h-28 place-items-center rounded-xl border border-dashed border-white/15 text-sm text-neutral-400">
          讀取儲存設定中…
        </p>
      ) : null}
      {!loading && !payload && !loadFailed ? (
        <p className="grid min-h-28 place-items-center rounded-xl border border-dashed border-white/15 text-sm text-neutral-400">
          尚無可編輯的儲存設定。
        </p>
      ) : null}
      {payload ? (
        <div className="grid min-w-0 gap-3 min-[720px]:grid-cols-2">
          {STORAGE_PATH_FIELDS.map((field) => (
            <TextInput
              id={`storage-${field.key}`}
              key={field.key}
              label={field.label}
              value={paths[field.key] ?? ""}
              onValueChange={(value) => updateField(["paths", field.key], value)}
              description={field.description}
              required
            />
          ))}
        </div>
      ) : null}
    </SettingPanel>
  );
}

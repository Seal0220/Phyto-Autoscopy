"use client";

import { FiSave } from "react-icons/fi";

import Button from "@/components/buttons/Button";
import SettingPanel from "@/components/panels/SettingPanel";
import useSettings from "@/hooks/useSettings";
import {
  imagePreviewSettingsSections,
  serializeImagePreviewSettingsPayload,
} from "@/features/ImagePreview/lib/imagePreviewUtils";

import ImagePreviewField from "./ImagePreviewField";

export default function ImagePreviewSettings({
  onNotify,
  open = false,
  locked = false,
}) {
  const {
    payload,
    loading,
    saving,
    loadFailed,
    updateField,
    saveGroup,
  } = useSettings({
    group: "cameras",
    onNotify,
    open,
    serializePayload: serializeImagePreviewSettingsPayload,
  });
  const sections = payload ? imagePreviewSettingsSections(payload) : [];

  return (
    <SettingPanel
      label="影像預覽"
      open={open}
      locked={locked}
      contentClassName="p-0"
      fieldsetClassName="gap-0"
      footerDividerClassName="mt-0! mb-4!"
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
          {saving ? "儲存中…" : "儲存影像預覽設定"}
        </Button>
      )}
    >
      {loading && !payload ? (
        <p className="grid min-h-28 place-items-center rounded-xl border border-dashed border-white/15 text-sm text-neutral-400">
          讀取設定中…
        </p>
      ) : null}
      {!loading && !payload && !loadFailed ? (
        <p className="grid min-h-28 place-items-center rounded-xl border border-dashed border-white/15 text-sm text-neutral-400">
          尚無可編輯設定。
        </p>
      ) : null}
      {payload ? (
        <div className="grid min-w-0 grid-cols-1 min-[720px]:grid-cols-2 min-[1180px]:grid-cols-3">
          {sections.map(({
            imagePreviewId,
            leaves,
          }) => {
            const enabledLeaves = leaves.filter(
              (leaf) => leaf.path.at(-1) === "enabled",
            );
            const inputLeaves = leaves.filter(
              (leaf) => leaf.path.at(-1) !== "enabled",
            );

            return (
              <section
                className="grid min-w-0 content-start gap-3 border-b border-white/10 px-3 py-5 last:border-b-0 min-[720px]:border-r min-[720px]:nth-[2n]:border-r-0 min-[1180px]:border-b-0 min-[1180px]:nth-[2n]:border-r min-[1180px]:nth-[3n]:border-r-0"
                key={imagePreviewId}
              >
                {enabledLeaves.map((leaf) => (
                  <ImagePreviewField
                    key={leaf.path.join(".")}
                    leaf={leaf}
                    onChange={updateField}
                  />
                ))}
                <div className="grid grid-cols-1 gap-3 min-[520px]:grid-cols-2 min-[1600px]:grid-cols-3">
                  {inputLeaves.map((leaf) => (
                    <ImagePreviewField
                      key={leaf.path.join(".")}
                      leaf={leaf}
                      onChange={updateField}
                    />
                  ))}
                </div>
              </section>
            );
          })}
        </div>
      ) : null}
    </SettingPanel>
  );
}

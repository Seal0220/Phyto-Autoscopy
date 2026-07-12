"use client";

import ActionRow from "@/components/actions/ActionRow";
import Button from "@/components/buttons/Button";
import SettingPanel from "@/components/panels/SettingPanel";
import useSettings from "@/hooks/useSettings";

import Section from "./components/Section";
import { groupedVisibleSettings } from "./lib/settingsUtils";

export default function Settings({
  group,
  label,
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
    group,
    onNotify,
    open,
  });
  const sections = payload ? groupedVisibleSettings(group, payload) : [];

  return (
    <SettingPanel
      label={label}
      open={open}
      locked={locked}
    >
      {loading && !payload ? <p className="grid min-h-28 place-items-center rounded-xl border border-dashed border-white/15 text-sm text-neutral-400">讀取設定中…</p> : null}
      {!loading && !payload && !loadFailed ? <p className="grid min-h-28 place-items-center rounded-xl border border-dashed border-white/15 text-sm text-neutral-400">尚無可編輯設定。</p> : null}
      {payload ? (
        <div className="grid min-w-0 gap-4 min-[720px]:grid-cols-2">
          {sections.map(({
            section,
            leaves,
          }) => (
            <Section
              key={section}
              group={group}
              section={section}
              leaves={leaves}
              onChange={updateField}
            />
          ))}
        </div>
      ) : null}
      <ActionRow>
        <Button
          variant="primary"
          onClick={() => void saveGroup()}
          disabled={!payload || saving || loading}
        >
          {saving ? "儲存中…" : `儲存${label}設定`}
        </Button>
      </ActionRow>
    </SettingPanel>
  );
}

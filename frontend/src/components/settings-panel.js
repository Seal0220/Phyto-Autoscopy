"use client";

import SettingsSection from "@/components/settings/settings-section";
import ActionRow from "@/components/ui/action-row";
import Button from "@/components/ui/button";
import useSettingsPanel from "@/hooks/use-settings-panel";
import { groupedVisibleSettings } from "@/lib/settings";

export default function SettingsPanel({
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
  } = useSettingsPanel({ group, onNotify, open });
  const sections = payload ? groupedVisibleSettings(group, payload) : [];

  return (
    <section className={`grid transition-[grid-template-rows,opacity] duration-200 ease-out motion-reduce:transition-none ${open ? "grid-rows-[1fr] opacity-100" : "pointer-events-none grid-rows-[0fr] opacity-0"}`} aria-label={`${label}設定`} aria-hidden={!open}>
      <div className={`min-h-0 ${open ? "overflow-visible" : "overflow-hidden"}`}>
        <div className={`rounded-b-[27px] border-t border-white/10 bg-black/20 ${group === "cameras" ? "p-0" : "px-5 py-8 max-sm:px-4"}`}>
          <fieldset
            className={`grid min-w-0 gap-4 border-0 p-0 ${locked ? "grayscale opacity-60" : ""}`}
            disabled={locked}
          >
            {loading && !payload ? <p className="grid min-h-28 place-items-center rounded-xl border border-dashed border-white/15 text-sm text-neutral-400">讀取設定中…</p> : null}
            {!loading && !payload && !loadFailed ? <p className="grid min-h-28 place-items-center rounded-xl border border-dashed border-white/15 text-sm text-neutral-400">尚無可編輯設定。</p> : null}
            {payload ? (
              <div className={`grid min-w-0 ${group === "cameras" ? "grid-cols-1 min-[720px]:grid-cols-2 min-[1180px]:grid-cols-3" : "gap-4 min-[720px]:grid-cols-2"}`}>
                {sections.map(({ section, leaves }) => (
                  <SettingsSection
                    key={section}
                    group={group}
                    section={section}
                    leaves={leaves}
                    onChange={updateField}
                  />
                ))}
              </div>
            ) : null}
            <ActionRow className={group === "cameras" ? "px-3 pb-5" : ""}>
              <Button variant="primary" onClick={() => void saveGroup()} disabled={!payload || saving || loading}>
                {saving ? "儲存中…" : `儲存${label}設定`}
              </Button>
            </ActionRow>
          </fieldset>
        </div>
      </div>
    </section>
  );
}

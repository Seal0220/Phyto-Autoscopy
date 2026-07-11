"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import {
  cloneValue,
  fieldMeta,
  groupedVisibleSettings,
  sectionMeta,
  serializeSettingsPayload,
  setNestedValue,
} from "@/lib/settings";
import Button from "@/components/ui/button";
import { NumericField, SelectField, TextField } from "@/components/ui/field";
import ToggleRow from "@/components/ui/toggle-row";

function fieldId(group, path) {
  return `setting-${group}-${path.join("-")}`;
}

function BooleanField({ group, leaf, onChange }) {
  const meta = fieldMeta(leaf);
  const enabled = Boolean(leaf.value);
  return <ToggleRow checked={enabled} label={meta.label} description={meta.description} onClick={() => onChange(leaf.path, !enabled)} />;
}

function StandardField({ group, leaf, onChange }) {
  const meta = fieldMeta(leaf);
  const id = fieldId(group, leaf.path);
  const value = leaf.value ?? "";
  const isNumber = meta.type === "number";
  const update = (nextValue) => onChange(leaf.path, nextValue);
  if (meta.type === "select") return <SelectField id={id} label={meta.label} value={value} onValueChange={update} options={meta.options} description={meta.description} />;
  if (isNumber) return <NumericField id={id} label={meta.label} value={value} onValueChange={update} min={meta.min} max={meta.max} step={meta.step} suffix={meta.suffix} description={meta.description} />;
  return <TextField id={id} label={meta.label} value={value} onValueChange={update} description={meta.description} />;
}

function SettingsField({ group, leaf, onChange }) {
  return typeof leaf.value === "boolean" ? (
    <BooleanField group={group} leaf={leaf} onChange={onChange} />
  ) : (
    <StandardField group={group} leaf={leaf} onChange={onChange} />
  );
}

export default function SettingsPanel({ group, label, onNotify, open = false }) {
  const [payload, setPayload] = useState(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [loadFailed, setLoadFailed] = useState(false);
  const hasLoadedRef = useRef(false);

  const loadGroup = useCallback(async () => {
    setLoading(true);
    setLoadFailed(false);
    try {
      const response = await fetch(`/api/settings/${group}`, { cache: "no-store" });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.detail || "讀取設定失敗。");
      }
      setPayload(cloneValue(payload));
    } catch (error) {
      setLoadFailed(true);
      onNotify?.(error.message || "讀取設定失敗。", "error");
    } finally {
      setLoading(false);
    }
  }, [group, onNotify]);

  useEffect(() => {
    if (!open || hasLoadedRef.current) return;
    hasLoadedRef.current = true;
    void loadGroup();
  }, [loadGroup, open]);

  function updateField(path, value) {
    setPayload((previous) => {
      if (!previous) return previous;
      const nextPayload = cloneValue(previous);
      setNestedValue(nextPayload, path, value);
      return nextPayload;
    });
  }

  async function saveGroup() {
    if (!payload) return;
    setSaving(true);
    try {
      const nextPayload = serializeSettingsPayload(group, payload);
      const response = await fetch(`/api/settings/${group}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ payload: nextPayload }),
      });
      const result = await response.json();
      if (!response.ok) {
        throw new Error(result.detail || "儲存設定失敗。");
      }
      setPayload(nextPayload);
      onNotify?.("已儲存並立即套用。", "success");
    } catch (error) {
      onNotify?.(error.message || "儲存設定失敗。", "error");
    } finally {
      setSaving(false);
    }
  }

  const sections = payload ? groupedVisibleSettings(group, payload) : [];

  return (
    <section className={`grid transition-[grid-template-rows,opacity] duration-200 ease-out motion-reduce:transition-none ${open ? "grid-rows-[1fr] opacity-100" : "pointer-events-none grid-rows-[0fr] opacity-0"}`} aria-label={`${label}設定`} aria-hidden={!open}>
      <div className={`min-h-0 ${open ? "overflow-visible" : "overflow-hidden"}`}>
      <div className="border-t border-white/10 bg-black/8 px-5 py-4 max-sm:px-4">
      {group !== "cameras" ? (
        <div className="mb-4 flex min-w-0 items-center">
          <div>
            <h3 className="m-0 text-base font-black text-white">{label}設定</h3>
          </div>
        </div>
      ) : null}

      <div className="grid min-w-0 gap-4">
        {loading && !payload ? <p className="grid min-h-28 place-items-center rounded-xl border border-dashed border-white/15 text-sm text-white/60">讀取設定中…</p> : null}
        {!loading && !payload && !loadFailed ? <p className="grid min-h-28 place-items-center rounded-xl border border-dashed border-white/15 text-sm text-white/60">尚無可編輯設定。</p> : null}
        {payload ? (
          <div className={`grid min-w-0 gap-4 ${group === "cameras" ? "min-[900px]:grid-cols-3 min-[720px]:grid-cols-2" : "min-[720px]:grid-cols-2"}`}>
            {sections.map(({ section, leaves }) => {
              const meta = sectionMeta(group, section);
              return (
                <section className={`${group === "cameras" ? "min-w-0 border-r border-white/10 pr-4 last:border-r-0" : "min-w-0"}`} key={section}>
                  <header className="mb-3">
                    <h3 className="m-0 text-sm font-black text-white">{meta.title}</h3>
                    {meta.description ? <p className="mt-1 text-xs font-semibold leading-5 text-white/55">{meta.description}</p> : null}
                  </header>
                  <div className="grid gap-3">
                    {leaves.map((leaf) => <SettingsField key={leaf.path.join(".")} group={group} leaf={leaf} onChange={updateField} />)}
                  </div>
                </section>
              );
            })}
          </div>
        ) : null}

        <div className="flex min-h-11 justify-center border-t border-white/10 pt-4">
          <Button variant="primary" onClick={() => void saveGroup()} disabled={!payload || saving || loading}>
            {saving ? "儲存中…" : `儲存${label}設定`}
          </Button>
        </div>
      </div>
      </div>
      </div>
    </section>
  );
}

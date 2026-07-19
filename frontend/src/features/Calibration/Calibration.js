"use client";

import {
  useEffect,
  useState,
} from "react";
import { useRouter } from "next/navigation";
import { FiRefreshCw } from "react-icons/fi";

import Button from "@/components/buttons/Button";
import StatusCard from "@/components/cards/StatusCard";
import RetryMessage from "@/components/feedback/RetryMessage";
import {
  Panel,
  PanelHeader,
} from "@/components/panels/Panel";
import SettingPanel from "@/components/panels/SettingPanel";
import SettingsGear from "@/components/panels/SettingsGear";
import useNotificationsContext from "@/features/Notifications/hooks/useNotificationsContext";

import CalibrationCreateForm from "./components/CalibrationCreateForm";
import CalibrationProfileList from "./components/CalibrationProfileList";
import useCalibrationCatalog from "./hooks/useCalibrationCatalog";

export default function Calibration() {
  const router = useRouter();
  const { showNotification } = useNotificationsContext();
  const [settingsOpen, setSettingsOpen] = useState(false);
  const {
    profiles,
    sourceImages,
    loading,
    loadError,
    createPending,
    createError,
    createRequiresRefresh,
    load,
    create,
    clearCreateError,
  } = useCalibrationCatalog();
  const validCount = profiles.filter((profile) => profile.valid).length;
  const staleCount = profiles.filter(
    (profile) => profile.potentially_invalid_reasons?.length,
  ).length;
  const hasCatalog = profiles.length > 0 || sourceImages.length > 0;

  useEffect(() => {
    if (loadError) showNotification(loadError, "error");
  }, [
    loadError,
    showNotification,
  ]);

  useEffect(() => {
    if (createError) showNotification(createError, "error");
  }, [
    createError,
    showNotification,
  ]);

  async function handleCreate(payload) {
    const profile = await create(payload);
    if (!profile?.calibration_id) return;

    showNotification("已建立相機校正項目。", "success");
    router.push(
      `/analysis/calibration/${encodeURIComponent(profile.calibration_id)}`,
    );
  }

  return (
    <Panel
      id="camera-calibration"
      aria-label="相機校正"
    >
      <PanelHeader
        title="相機校正"
        action={(
          <div className="flex flex-wrap items-center justify-end gap-2">
            <Button
              disabled={loading || createPending}
              onClick={() => void load()}
            >
              <FiRefreshCw
                className="size-4 shrink-0"
                aria-hidden="true"
              />
              {loading ? "讀取中…" : "重新讀取"}
            </Button>
            <SettingsGear
              label="相機校正"
              open={settingsOpen}
              onClick={() => setSettingsOpen((current) => !current)}
            />
          </div>
        )}
      />

      <div className="grid gap-4 p-5 max-sm:p-4">
        {loadError ? (
          <RetryMessage
            message={loadError}
            onRetry={() => void load()}
            retrying={loading}
          />
        ) : null}

        {loading && !hasCatalog ? (
          <div
            className="grid min-h-32 place-items-center rounded-xl border border-white/10 bg-black/10 p-4 text-sm font-semibold text-neutral-400"
            role="status"
          >
            讀取校正結果與項目中…
          </div>
        ) : null}

        {(!loadError || hasCatalog) && (!loading || hasCatalog) ? (
          <>
            <div className="grid gap-3 min-[520px]:grid-cols-3">
              <StatusCard
                title="校正項目"
                content={profiles.length}
                note="組"
              />
              <StatusCard
                title="有效校正"
                content={validCount}
                note="組"
              />
              <StatusCard
                title="可能失效"
                content={staleCount}
                note="組"
              />
            </div>
            <CalibrationProfileList profiles={profiles} />
          </>
        ) : null}
      </div>

      <SettingPanel
        label="相機校正"
        open={settingsOpen}
      >
        <CalibrationCreateForm
          sourceImages={sourceImages}
          pending={createPending}
          error={createError}
          requiresRefresh={createRequiresRefresh}
          onCreate={handleCreate}
          onClearError={clearCreateError}
          onRefresh={() => void load()}
        />
      </SettingPanel>
    </Panel>
  );
}

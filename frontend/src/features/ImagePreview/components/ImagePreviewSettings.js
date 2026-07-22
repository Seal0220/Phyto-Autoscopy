"use client";

import {
  useEffect,
  useRef,
} from "react";
import {
  FiRefreshCw,
  FiSave,
} from "react-icons/fi";

import Button from "@/components/buttons/Button";
import RetryMessage from "@/components/feedback/RetryMessage";
import SubsectionHeader from "@/components/headers/SubsectionHeader";
import SettingPanel from "@/components/panels/SettingPanel";
import useSettings from "@/hooks/useSettings";
import useImagePreviewDevices from "@/features/ImagePreview/hooks/useImagePreviewDevices";
import {
  emitCameraSettingsUpdated,
  subscribeCameraSettingsUpdated,
} from "@/lib/settingsEvents";
import {
  imagePreviewFieldMeta,
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
    loadError,
    loadGroup,
    updateField,
    saveGroup,
  } = useSettings({
    group: "cameras",
    onNotify,
    open,
    serializePayload: serializeImagePreviewSettingsPayload,
  });
  const sections = payload ? imagePreviewSettingsSections(payload) : [];
  const {
    scanResults,
    scanning,
    scanDevices,
  } = useImagePreviewDevices({
    open,
    onNotify,
  });
  const mockMode = scanResults.some((result) => result?.mock);
  const mockNoticeShownRef = useRef(false);

  useEffect(() => {
    if (!mockMode || mockNoticeShownRef.current) return;

    mockNoticeShownRef.current = true;
    onNotify?.(
      "目前使用模擬相機來源。",
      "info",
    );
  }, [
    mockMode,
    onNotify,
  ]);

  function updateImagePreviewField(
    path,
    value,
  ) {
    const isDeviceIndex = path.at(-1) === "device_index";
    const nextValue = isDeviceIndex && value === ""
      ? null
      : value;

    updateField(path, nextValue);

    if (isDeviceIndex && nextValue === null) {
      updateField(
        [...path.slice(0, -1), "enabled"],
        false,
      );
    }
  }

  useEffect(() => subscribeCameraSettingsUpdated((event) => {
    if (event.detail?.cameraId !== "rotating") return;
    if (!Object.hasOwn(event.detail, "armHeightMm")) return;

    updateField(
      ["cameras", "rotating", "arm_height_mm"],
      event.detail.armHeightMm,
    );
  }), [updateField]);

  async function saveCameraSettings() {
    const armHeightMm = payload?.cameras?.rotating?.arm_height_mm ?? null;
    const saved = await saveGroup();

    if (saved) {
      emitCameraSettingsUpdated({
        cameraId: "rotating",
        armHeightMm,
      });
    }
  }

  return (
    <SettingPanel
      label="攝影機"
      open={open}
      locked={locked || saving}
      contentClassName="p-0"
      fieldsetClassName="gap-0"
      footerDividerClassName="mt-0! mb-4!"
      footer={(
        <>
          <Button
            onClick={() => void scanDevices()}
            disabled={scanning || loading || saving}
          >
            <FiRefreshCw
              className={`
                size-4 shrink-0
                ${scanning ? "animate-spin motion-reduce:animate-none" : ""}
              `}
              aria-hidden="true"
            />
            {scanning ? "掃描中…" : "重新掃描裝置"}
          </Button>
          <Button
            variant="primary"
            onClick={() => void saveCameraSettings()}
            disabled={!payload || saving || loading}
          >
            <FiSave
              className="size-4 shrink-0"
              aria-hidden="true"
            />
            {saving ? "儲存中…" : "儲存攝影機設定"}
          </Button>
        </>
      )}
    >
      {loading && !payload ? (
        <p className="grid min-h-28 place-items-center rounded-xl border border-dashed border-white/15 text-sm text-neutral-400">
          讀取設定中…
        </p>
      ) : null}
      {!loading && !payload && loadFailed ? (
        <RetryMessage
          message={loadError || "讀取攝影機設定失敗。"}
          onRetry={() => void loadGroup()}
          retrying={loading}
        />
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
            const installationLeaves = inputLeaves.filter(
              (leaf) => imagePreviewFieldMeta(leaf).group === "installation",
            );
            const cameraLeaves = inputLeaves.filter(
              (leaf) => imagePreviewFieldMeta(leaf).group !== "installation",
            );

            return (
              <section
                className="grid min-w-0 content-start gap-3 border-b border-white/15 px-3 py-5 last:border-b-0 min-[720px]:border-r min-[720px]:nth-[2n]:border-r-0 min-[1180px]:border-b-0 min-[1180px]:nth-[2n]:border-r min-[1180px]:nth-[3n]:border-r-0"
                key={imagePreviewId}
              >
                {enabledLeaves.map((leaf) => (
                  <ImagePreviewField
                    key={leaf.path.join(".")}
                    leaf={leaf}
                    onChange={updateImagePreviewField}
                    scanResults={scanResults}
                    cameraDrafts={payload.cameras}
                  />
                ))}
                <div className="grid grid-cols-1 gap-3 min-[520px]:grid-cols-2 min-[1600px]:grid-cols-3">
                  {cameraLeaves.map((leaf) => (
                    <ImagePreviewField
                      key={leaf.path.join(".")}
                      leaf={leaf}
                      onChange={updateImagePreviewField}
                      scanResults={scanResults}
                      cameraDrafts={payload.cameras}
                    />
                  ))}
                </div>
                {installationLeaves.length ? (
                  <>
                    {/* <SubsectionHeader
                      title="相機安裝參數"
                      description="作為分析姿態估計的初始值與合理性檢查依據。"
                      titleMode={1}
                    /> */}
                    <hr className="my-1!"/>
                    <div className="grid grid-cols-1 gap-3 min-[520px]:grid-cols-2 min-[1600px]:grid-cols-3">
                      {installationLeaves.map((leaf) => (
                        <ImagePreviewField
                          key={leaf.path.join(".")}
                          leaf={leaf}
                          onChange={updateImagePreviewField}
                          scanResults={scanResults}
                          cameraDrafts={payload.cameras}
                        />
                      ))}
                    </div>
                  </>
                ) : null}
              </section>
            );
          })}
        </div>
      ) : null}
    </SettingPanel>
  );
}

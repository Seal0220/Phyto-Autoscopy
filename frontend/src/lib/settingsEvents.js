import { invalidatePageData } from "@/lib/pageDataCache";

export const CAMERA_SETTINGS_UPDATED_EVENT = "phyto:camera-settings-updated";

export function emitCameraSettingsUpdated(detail) {
  if (typeof window === "undefined") return;
  invalidatePageData("settings:cameras");
  invalidatePageData("calibration:");
  invalidatePageData("analysis:");

  window.dispatchEvent(new CustomEvent(
    CAMERA_SETTINGS_UPDATED_EVENT,
    { detail },
  ));
}

export function subscribeCameraSettingsUpdated(listener) {
  if (typeof window === "undefined") return () => {};

  window.addEventListener(CAMERA_SETTINGS_UPDATED_EVENT, listener);
  return () => window.removeEventListener(
    CAMERA_SETTINGS_UPDATED_EVENT,
    listener,
  );
}

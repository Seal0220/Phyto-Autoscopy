"use client";

import {
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";

import { cloneValue } from "@/features/Settings/lib/settingsUtils";
import {
  abortRequest,
  messageFromError,
  parseJsonResponse,
  responseErrorMessage,
} from "@/lib/httpUtils";
import {
  emitCameraSettingsUpdated,
  subscribeCameraSettingsUpdated,
} from "@/lib/settingsEvents";

import {
  INITIAL_SCHEDULE,
} from "../scheduleConfig";
import {
  buildSchedulePayload,
  scheduleWithRotationEnabled,
} from "../lib/scheduleUtils";

export default function useSchedule({
  onNotify,
  onRunAction,
  onStarted,
}) {
  const [schedule, setSchedule] = useState(INITIAL_SCHEDULE);
  const [defaultsLoading, setDefaultsLoading] = useState(true);
  const [defaultsSaving, setDefaultsSaving] = useState(false);
  const [defaultsLoadError, setDefaultsLoadError] = useState("");
  const loadingDefaultsRef = useRef(false);
  const savingDefaultsRef = useRef(false);
  const mountedRef = useRef(false);
  const defaultsAbortRef = useRef(null);
  const saveDefaultsAbortRef = useRef(null);
  const settingsPayloadsRef = useRef(null);

  useEffect(() => {
    mountedRef.current = true;

    return () => {
      const controller = defaultsAbortRef.current;
      const saveController = saveDefaultsAbortRef.current;

      mountedRef.current = false;
      loadingDefaultsRef.current = false;
      savingDefaultsRef.current = false;
      defaultsAbortRef.current = null;
      saveDefaultsAbortRef.current = null;
      settingsPayloadsRef.current = null;
      abortRequest(controller);
      abortRequest(saveController);
    };
  }, []);

  useEffect(() => subscribeCameraSettingsUpdated((event) => {
    if (event.detail?.cameraId !== "rotating") return;
    if (!Object.hasOwn(event.detail, "armHeightMm")) return;

    setSchedule((previous) => ({
      ...previous,
      arm_height_mm: event.detail.armHeightMm ?? "",
    }));
  }), []);

  const loadDefaults = useCallback(async () => {
    if (loadingDefaultsRef.current) return false;

    const controller = new AbortController();
    loadingDefaultsRef.current = true;
    defaultsAbortRef.current = controller;
    setDefaultsLoading(true);
    setDefaultsLoadError("");

    try {
      const [scheduleResponse, camerasResponse] = await Promise.all([
        fetch("/api/settings/schedule", {
          cache: "no-store",
          signal: controller.signal,
        }),
        fetch("/api/settings/cameras", {
          cache: "no-store",
          signal: controller.signal,
        }),
      ]);
      const [schedulePayload, camerasPayload] = await Promise.all([
        parseJsonResponse(scheduleResponse),
        parseJsonResponse(camerasResponse),
      ]);

      if (!scheduleResponse.ok) {
        throw new Error(responseErrorMessage(
          schedulePayload,
          "讀取排程預設失敗。",
        ));
      }
      if (!camerasResponse.ok) {
        throw new Error(responseErrorMessage(
          camerasPayload,
          "讀取攝影機設定失敗。",
        ));
      }

      if (
        !schedulePayload.schedule
        || typeof schedulePayload.schedule !== "object"
        || Array.isArray(schedulePayload.schedule)
        || !camerasPayload.cameras
        || typeof camerasPayload.cameras !== "object"
        || Array.isArray(camerasPayload.cameras)
      ) {
        throw new Error("排程或攝影機設定格式錯誤，請重新讀取。");
      }

      if (!mountedRef.current || controller.signal.aborted) return false;

      settingsPayloadsRef.current = {
        schedule: cloneValue(schedulePayload),
        cameras: cloneValue(camerasPayload),
      };
      const scheduleSettings = schedulePayload.schedule;
      const rotatingCamera = camerasPayload.cameras.rotating || {};
      const rotationEnabled = scheduleSettings.rotation_enabled
        ?? INITIAL_SCHEDULE.rotation_enabled;

      setSchedule((previous) => scheduleWithRotationEnabled({
        rotation_enabled: rotationEnabled,
        duration_seconds: String(
          scheduleSettings.duration_seconds ?? INITIAL_SCHEDULE.duration_seconds,
        ),
        total_cycles: String(
          scheduleSettings.total_cycles ?? INITIAL_SCHEDULE.total_cycles,
        ),
        cycle_interval_seconds: String(
          scheduleSettings.cycle_interval_seconds
            ?? INITIAL_SCHEDULE.cycle_interval_seconds,
        ),
        rotation_start_deg: String(
          scheduleSettings.rotation_start_deg ?? INITIAL_SCHEDULE.rotation_start_deg,
        ),
        rotation_end_deg: String(
          scheduleSettings.rotation_end_deg ?? INITIAL_SCHEDULE.rotation_end_deg,
        ),
        angle_tolerance_deg: String(
          scheduleSettings.angle_tolerance_deg ?? INITIAL_SCHEDULE.angle_tolerance_deg,
        ),
        stabilization_delay_ms: String(
          scheduleSettings.stabilization_delay_ms
            ?? INITIAL_SCHEDULE.stabilization_delay_ms,
        ),
        capture_on_return: scheduleSettings.capture_on_return
          ?? INITIAL_SCHEDULE.capture_on_return,
        return_to_origin: scheduleSettings.return_to_origin
          ?? INITIAL_SCHEDULE.return_to_origin,
        arm_height_mm: rotatingCamera.arm_height_mm ?? "",
        modes: previous.modes.map((mode, index) => (
          index === 0
            && ["continuous_interval", "time_interval"].includes(mode.type)
            ? {
              ...mode,
              interval_seconds: String(
                scheduleSettings.capture_interval_seconds ?? mode.interval_seconds,
              ),
            }
            : mode
        )),
      }, rotationEnabled));
      setDefaultsLoadError("");
      return true;
    } catch (error) {
      if (error?.name === "AbortError") return false;

      const message = messageFromError(error, "讀取排程預設失敗。");

      if (!mountedRef.current) return false;

      setDefaultsLoadError(message);
      onNotify(message, "error");
      return false;
    } finally {
      if (defaultsAbortRef.current === controller) {
        defaultsAbortRef.current = null;
        loadingDefaultsRef.current = false;

        if (mountedRef.current) {
          setDefaultsLoading(false);
        }
      }
    }
  }, [onNotify]);

  const saveDefaults = useCallback(async () => {
    if (savingDefaultsRef.current || !settingsPayloadsRef.current) return false;

    const stabilizationDelay = Number(schedule.stabilization_delay_ms);
    const armHeightText = String(schedule.arm_height_mm ?? "").trim();
    const armHeight = armHeightText === ""
      ? null
      : Number(armHeightText);
    let commonPayload;

    try {
      commonPayload = buildSchedulePayload(schedule);
    } catch (error) {
      onNotify(messageFromError(error, "排程通用配置無效。"), "error");
      return false;
    }

    if (!Number.isFinite(stabilizationDelay) || stabilizationDelay < 0) {
      onNotify("穩定等待必須是大於或等於 0 的有效時間。", "error");
      return false;
    }
    if (
      armHeight !== null
      && (
        !Number.isFinite(armHeight)
        || armHeight < 0
        || armHeight > 10000
      )
    ) {
      onNotify("旋臂高度必須介於 0 到 10000 mm。", "error");
      return false;
    }

    const controller = new AbortController();
    savingDefaultsRef.current = true;
    saveDefaultsAbortRef.current = controller;
    setDefaultsSaving(true);

    try {
      const [scheduleResponse, camerasResponse] = await Promise.all([
        fetch("/api/settings/schedule", {
          cache: "no-store",
          signal: controller.signal,
        }),
        fetch("/api/settings/cameras", {
          cache: "no-store",
          signal: controller.signal,
        }),
      ]);
      const [currentSchedulePayload, currentCamerasPayload] = await Promise.all([
        parseJsonResponse(scheduleResponse),
        parseJsonResponse(camerasResponse),
      ]);

      if (!scheduleResponse.ok || !camerasResponse.ok) {
        throw new Error("儲存前無法重新讀取最新設定，請稍後重試。");
      }

      const nextSchedulePayload = cloneValue(currentSchedulePayload);
      const nextCamerasPayload = cloneValue(currentCamerasPayload);
      nextSchedulePayload.schedule.rotation_enabled = commonPayload.rotation_enabled;
      nextSchedulePayload.schedule.duration_seconds = Number(
        schedule.duration_seconds,
      );
      delete nextSchedulePayload.schedule.cycle_duration_seconds;
      if (commonPayload.rotation_enabled) {
        nextSchedulePayload.schedule.total_cycles = commonPayload.total_cycles;
        nextSchedulePayload.schedule.cycle_interval_seconds = (
          commonPayload.cycle_interval_seconds
        );
        nextSchedulePayload.schedule.rotation_start_deg = (
          commonPayload.rotation_start_deg
        );
        nextSchedulePayload.schedule.rotation_end_deg = (
          commonPayload.rotation_end_deg
        );
        nextSchedulePayload.schedule.angle_tolerance_deg = (
          commonPayload.angle_tolerance_deg
        );
      }
      const firstIntervalMode = commonPayload.modes.find(
        (mode) => ["continuous_interval", "time_interval"].includes(mode.type),
      );
      if (firstIntervalMode) {
        nextSchedulePayload.schedule.capture_interval_seconds = (
          firstIntervalMode.interval_seconds
        );
      }
      nextSchedulePayload.schedule.stabilization_delay_ms = Math.round(
        stabilizationDelay,
      );
      nextSchedulePayload.schedule.capture_on_return = Boolean(
        schedule.capture_on_return,
      );
      nextSchedulePayload.schedule.return_to_origin = Boolean(
        schedule.return_to_origin,
      );
      nextCamerasPayload.cameras.rotating.arm_height_mm = armHeight;

      const response = await fetch("/api/settings/batch", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          payloads: {
            schedule: nextSchedulePayload,
            cameras: nextCamerasPayload,
          },
        }),
        signal: controller.signal,
      });
      const result = await parseJsonResponse(response);

      if (!response.ok) {
        throw new Error(responseErrorMessage(
          result,
          "儲存排程通用配置失敗。",
        ));
      }
      if (
        result?.applied !== true
        || !Array.isArray(result.updated)
        || !result.updated.includes("schedule")
        || !result.updated.includes("cameras")
      ) {
        throw new Error("儲存排程通用配置的回應格式錯誤。請重新讀取確認。");
      }
      if (!mountedRef.current || controller.signal.aborted) return false;

      settingsPayloadsRef.current = {
        schedule: nextSchedulePayload,
        cameras: nextCamerasPayload,
      };
      emitCameraSettingsUpdated({
        cameraId: "rotating",
        armHeightMm: armHeight,
      });
      onNotify("排程設定與旋臂高度已同步。", "success");
      return true;
    } catch (error) {
      if (error?.name === "AbortError") return false;
      if (mountedRef.current) {
        onNotify(
          messageFromError(error, "儲存排程通用配置失敗。"),
          "error",
        );
      }
      return false;
    } finally {
      if (saveDefaultsAbortRef.current === controller) {
        saveDefaultsAbortRef.current = null;
        savingDefaultsRef.current = false;
        if (mountedRef.current) setDefaultsSaving(false);
      }
    }
  }, [
    onNotify,
    schedule,
  ]);

  useEffect(() => {
    void loadDefaults();
  }, [loadDefaults]);

  async function handleSubmit(event) {
    event.preventDefault();

    if (defaultsLoading) {
      onNotify("排程預設仍在讀取中，請稍候再開始。", "warning");
      return;
    }
    if (defaultsSaving) {
      onNotify("通用配置仍在儲存中，請稍候再開始。", "warning");
      return;
    }

    let payload;

    try {
      payload = buildSchedulePayload(schedule);
    } catch (error) {
      onNotify(messageFromError(error, "排程內容無效。"), "error");
      return;
    }

    const result = await onRunAction("schedule.start", payload, "排程已開始。");

    if (result) {
      void onStarted?.();
    }
  }

  return {
    schedule,
    setSchedule,
    defaultsLoading,
    defaultsSaving,
    defaultsLoadError,
    loadDefaults,
    saveDefaults,
    handleSubmit,
  };
}

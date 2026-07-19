"use client";

import {
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";

import {
  abortRequest,
  messageFromError,
  parseJsonResponse,
  responseErrorMessage,
} from "@/lib/httpUtils";

import {
  INITIAL_SCHEDULE,
} from "../scheduleConfig";
import {
  buildSchedulePayload,
} from "../lib/scheduleUtils";

export default function useSchedule({
  onNotify,
  onRunAction,
  onStarted,
}) {
  const [schedule, setSchedule] = useState(INITIAL_SCHEDULE);
  const [defaultsLoading, setDefaultsLoading] = useState(true);
  const [defaultsLoadError, setDefaultsLoadError] = useState("");
  const loadingDefaultsRef = useRef(false);
  const mountedRef = useRef(false);
  const defaultsAbortRef = useRef(null);

  useEffect(() => {
    mountedRef.current = true;

    return () => {
      const controller = defaultsAbortRef.current;

      mountedRef.current = false;
      loadingDefaultsRef.current = false;
      defaultsAbortRef.current = null;
      abortRequest(controller);
    };
  }, []);

  const loadDefaults = useCallback(async () => {
    if (loadingDefaultsRef.current) return false;

    const controller = new AbortController();
    loadingDefaultsRef.current = true;
    defaultsAbortRef.current = controller;
    setDefaultsLoading(true);
    setDefaultsLoadError("");

    try {
      const response = await fetch("/api/settings/schedule", {
        cache: "no-store",
        signal: controller.signal,
      });
      const payload = await parseJsonResponse(response);

      if (!response.ok) {
        throw new Error(responseErrorMessage(
          payload,
          "讀取排程預設失敗。",
        ));
      }

      if (
        !payload.schedule
        || typeof payload.schedule !== "object"
        || Array.isArray(payload.schedule)
      ) {
        throw new Error("排程預設資料格式錯誤，請重新讀取。");
      }

      if (!mountedRef.current || controller.signal.aborted) return false;

      const scheduleSettings = payload.schedule;

      setSchedule((previous) => ({
        duration_seconds: String(
          (scheduleSettings.duration_minutes ?? Number(INITIAL_SCHEDULE.duration_seconds) / 60) * 60,
        ),
        rotation_start_deg: String(
          scheduleSettings.rotation_start_deg ?? INITIAL_SCHEDULE.rotation_start_deg,
        ),
        rotation_end_deg: String(
          scheduleSettings.rotation_end_deg ?? INITIAL_SCHEDULE.rotation_end_deg,
        ),
        rotation_step_deg: String(
          scheduleSettings.rotation_step_deg ?? INITIAL_SCHEDULE.rotation_step_deg,
        ),
        angle_tolerance_deg: String(
          scheduleSettings.angle_tolerance_deg ?? INITIAL_SCHEDULE.angle_tolerance_deg,
        ),
        modes: previous.modes.map((mode, index) => (
          index === 0 && mode.type === "time_interval"
            ? {
              ...mode,
              interval_seconds: String(
                scheduleSettings.capture_interval_seconds ?? mode.interval_seconds,
              ),
            }
            : mode
        )),
      }));
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

  useEffect(() => {
    void loadDefaults();
  }, [loadDefaults]);

  async function handleSubmit(event) {
    event.preventDefault();

    if (defaultsLoading) {
      onNotify("排程預設仍在讀取中，請稍候再開始。", "warning");
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
    defaultsLoadError,
    loadDefaults,
    handleSubmit,
  };
}

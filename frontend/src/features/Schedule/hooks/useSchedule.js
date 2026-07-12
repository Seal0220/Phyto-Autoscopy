"use client";

import {
  useEffect,
  useState,
} from "react";

import { messageFromError, parseJsonResponse } from "@/lib/httpUtils";

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

  useEffect(() => {
    let active = true;

    async function loadDefaults() {
      try {
        const response = await fetch("/api/settings/experiment", {
          cache: "no-store",
        });
        const payload = await parseJsonResponse(response);

        if (!response.ok || !payload.experiment || !active) {
          return;
        }

        const experiment = payload.experiment;

        setSchedule((previous) => ({
          duration_seconds: String(
            (experiment.duration_minutes ?? Number(INITIAL_SCHEDULE.duration_seconds) / 60) * 60,
          ),
          rotation_start_deg: String(
            experiment.rotation_start_deg ?? INITIAL_SCHEDULE.rotation_start_deg,
          ),
          rotation_end_deg: String(
            experiment.rotation_end_deg ?? INITIAL_SCHEDULE.rotation_end_deg,
          ),
          rotation_step_deg: String(
            experiment.rotation_step_deg ?? INITIAL_SCHEDULE.rotation_step_deg,
          ),
          angle_tolerance_deg: String(
            experiment.angle_tolerance_deg ?? INITIAL_SCHEDULE.angle_tolerance_deg,
          ),
          modes: previous.modes.map((mode, index) => (
            index === 0 && mode.type === "seconds_interval"
              ? {
                ...mode,
                interval_seconds: String(
                  experiment.capture_interval_seconds ?? mode.interval_seconds,
                ),
              }
              : mode
          )),
        }));
      } catch {
        // Keep the live controls usable with safe defaults.
      }
    }

    void loadDefaults();

    return () => {
      active = false;
    };
  }, []);

  async function handleSubmit(event) {
    event.preventDefault();

    let payload;

    try {
      payload = buildSchedulePayload(schedule);
    } catch (error) {
      onNotify(messageFromError(error, "排程內容無效。"), "error");
      return;
    }

    const result = await onRunAction("experiment.start", payload, "排程已開始。");

    if (result) {
      void onStarted?.();
    }
  }

  return {
    schedule,
    setSchedule,
    handleSubmit,
  };
}

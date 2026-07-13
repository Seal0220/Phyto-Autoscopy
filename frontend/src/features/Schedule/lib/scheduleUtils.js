import {
  SCHEDULE_MODE_META,
  SCHEDULE_STATUS_LABELS,
  SCHEDULE_STATUS_TONES,
} from "../scheduleConfig";

function positiveNumber(
  value,
  label,
) {
  const parsed = Number(value);

  if (!Number.isFinite(parsed) || parsed <= 0) {
    throw new Error(`${label}必須大於 0。`);
  }

  return parsed;
}

export function scheduleStatusLabel(status) {
  return SCHEDULE_STATUS_LABELS[status] || "未知狀態";
}

export function scheduleStatusTone(status) {
  return SCHEDULE_STATUS_TONES[status] || "warning";
}

export function scheduleErrorMessage(value) {
  if (typeof value !== "string") return "排程執行失敗。";

  const message = value.trim();

  if (
    !message
    || message.length > 500
    || /[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/.test(message)
  ) {
    return "排程執行失敗。";
  }

  return message;
}

export function scheduleModeTypeFromLabel(label) {
  return Object.entries(SCHEDULE_MODE_META).find(([, meta]) => meta.label === label)?.[0] || "time_interval";
}

export function buildSchedulePayload(schedule) {
  const payload = {
    duration_seconds: Number(schedule.duration_seconds),
    rotation_start_deg: Number(schedule.rotation_start_deg),
    rotation_end_deg: Number(schedule.rotation_end_deg),
    rotation_step_deg: Number(schedule.rotation_step_deg),
    angle_tolerance_deg: Number(schedule.angle_tolerance_deg),
    modes: schedule.modes.map((mode) => {
      if (mode.type === "specific_angles") {
        const parts = mode.angles
          .split(",")
          .map((value) => value.trim())
          .filter(Boolean);
        const angles = parts.map(Number);

        if (!angles.length || angles.some((value) => !Number.isFinite(value))) {
          throw new Error("特定角度請使用逗號分隔的有效數字。");
        }

        return {
          id: mode.id,
          type: mode.type,
          angles,
        };
      }

      if (mode.type === "time_interval") {
        return {
          id: mode.id,
          type: mode.type,
          interval_seconds: positiveNumber(mode.interval_seconds, "時間間隔"),
        };
      }

      if (mode.type === "angle_interval") {
        return {
          id: mode.id,
          type: mode.type,
          interval_degrees: positiveNumber(mode.interval_degrees, "角度間隔"),
        };
      }

      const points = positiveNumber(mode.points, "等分點數");

      if (!Number.isInteger(points) || points < 2) {
        throw new Error("等分點數必須是至少 2 的整數。");
      }

      return {
        id: mode.id,
        type: mode.type,
        points,
      };
    }),
  };

  const invalidCommon = Object.entries(payload)
    .filter(([key]) => key !== "modes")
    .some(([, value]) => !Number.isFinite(value));

  if (invalidCommon) {
    throw new Error("排程共用控制必須是有效數字。");
  }

  if (
    payload.duration_seconds <= 0
    || payload.rotation_step_deg <= 0
    || payload.angle_tolerance_deg < 0
  ) {
    throw new Error("總時長與步進度數必須大於 0，角度誤差不可小於 0。");
  }

  if (payload.rotation_end_deg < payload.rotation_start_deg) {
    throw new Error("結束角度不可小於起始角度。");
  }

  if (!payload.modes.length) {
    throw new Error("請至少新增一個擷取模式。");
  }

  return payload;
}

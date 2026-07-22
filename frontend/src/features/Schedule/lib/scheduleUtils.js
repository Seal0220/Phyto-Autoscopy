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
  return Object.entries(SCHEDULE_MODE_META).find(([, meta]) => meta.label === label)?.[0] || "continuous_interval";
}

export function scheduleWithRotationEnabled(
  schedule,
  rotationEnabled,
) {
  if (rotationEnabled) {
    return {
      ...schedule,
      rotation_enabled: true,
    };
  }

  return {
    ...schedule,
    rotation_enabled: false,
    modes: schedule.modes.map((mode) => (
      mode.type === "continuous_interval"
        ? mode
        : {
          id: mode.id,
          type: "continuous_interval",
          ...SCHEDULE_MODE_META.continuous_interval.initial,
        }
    )),
  };
}

export function schedulePlannedDurationSeconds(schedule) {
  if (!schedule.rotation_enabled) {
    return Number(schedule.duration_seconds) || 0;
  }

  const totalCycles = Math.max(0, Number(schedule.total_cycles) || 0);
  const cycleDuration = Math.max(
    0,
    Number(schedule.cycle_duration_seconds) || 0,
  );
  const cycleInterval = Math.max(
    0,
    Number(schedule.cycle_interval_seconds) || 0,
  );
  return totalCycles * cycleDuration
    + Math.max(0, totalCycles - 1) * cycleInterval;
}

export function buildSchedulePayload(schedule) {
  const rotationEnabled = Boolean(schedule.rotation_enabled);
  const payload = {
    rotation_enabled: rotationEnabled,
    stabilization_delay_ms: Number(schedule.stabilization_delay_ms),
    capture_on_return: Boolean(schedule.capture_on_return),
    return_to_origin: Boolean(schedule.return_to_origin),
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

      if (["continuous_interval", "time_interval"].includes(mode.type)) {
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

  if (rotationEnabled) {
    payload.total_cycles = Number(schedule.total_cycles);
    payload.cycle_duration_seconds = Number(
      schedule.cycle_duration_seconds,
    );
    payload.cycle_interval_seconds = Number(
      schedule.cycle_interval_seconds,
    );
    payload.rotation_start_deg = Number(schedule.rotation_start_deg);
    payload.rotation_end_deg = Number(schedule.rotation_end_deg);
    payload.angle_tolerance_deg = Number(schedule.angle_tolerance_deg);
  } else {
    payload.duration_seconds = Number(schedule.duration_seconds);
  }

  const invalidCommon = Object.entries(payload)
    .filter(([key]) => ![
      "modes",
      "rotation_enabled",
      "capture_on_return",
      "return_to_origin",
    ].includes(key))
    .some(([, value]) => !Number.isFinite(value));

  if (invalidCommon) {
    throw new Error("排程共用控制必須是有效數字。");
  }

  if (
    !rotationEnabled
    && payload.duration_seconds <= 0
  ) {
    throw new Error("總時長必須大於 0。");
  }

  if (
    rotationEnabled
    && (
      !Number.isInteger(payload.total_cycles)
      || payload.total_cycles <= 0
    )
  ) {
    throw new Error("總輪數必須是大於 0 的整數。");
  }

  if (
    rotationEnabled
    && (
      payload.cycle_duration_seconds <= 0
      || payload.cycle_interval_seconds < 0
      || payload.angle_tolerance_deg < 0
      || payload.stabilization_delay_ms < 0
    )
  ) {
    throw new Error(
      "每輪時長必須大於 0，每輪間隔、角度誤差與穩定等待不可小於 0。",
    );
  }

  if (
    rotationEnabled
    && payload.rotation_end_deg < payload.rotation_start_deg
  ) {
    throw new Error("結束角度不可小於起始角度。");
  }

  if (!payload.modes.length) {
    throw new Error("請至少新增一個擷取模式。");
  }

  if (
    !rotationEnabled
    && payload.modes.some((mode) => mode.type !== "continuous_interval")
  ) {
    throw new Error("未啟用旋臂時只能使用連續間隔擷取模式。");
  }

  return payload;
}

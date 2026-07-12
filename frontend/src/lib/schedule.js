export const SCHEDULE_COMMON_DEFAULTS = {
  duration_seconds: "14400",
  rotation_start_deg: "0",
  rotation_end_deg: "360",
  rotation_step_deg: "1",
  angle_tolerance_deg: "0.5",
};

export const INITIAL_SCHEDULE = {
  ...SCHEDULE_COMMON_DEFAULTS,
  modes: [
    { id: "mode-1", type: "seconds_interval", interval_seconds: "60" },
  ],
};

export const SCHEDULE_DURATION_FIELD = ["duration_seconds", "總時長", { unit: "seconds" }];

export const SCHEDULE_COMMON_FIELDS = [
  ["rotation_start_deg", "起始角度", { min: 0, max: 360, step: 0.1, suffix: "度" }],
  ["rotation_end_deg", "結束角度", { min: 0, max: 360, step: 0.1, suffix: "度" }],
  ["rotation_step_deg", "步進度數", { min: 0.1, max: 360, step: 0.1, suffix: "度" }],
  ["angle_tolerance_deg", "角度誤差", { min: 0, max: 180, step: 0.1, suffix: "± 度" }],
];

export const SCHEDULE_MODE_META = {
  seconds_interval: {
    label: "時間間隔擷取",
    description: "依設定時間間隔擷取一次。",
    initial: { interval_seconds: "60" },
  },
  angle_interval: {
    label: "角度間隔擷取",
    description: "從起始角度開始，每隔指定角度擷取一次。",
    initial: { interval_degrees: "15" },
  },
  specific_angles: {
    label: "特定角度擷取",
    description: "在不同特定角度擷取一次，以逗號分隔，例如：30,45,60,122。",
    initial: { angles: "30,45,60,122" },
  },
  equal_divisions: {
    label: "等分擷取",
    description: "在起始與結束角度之間，平均等分指定數量的擷取點，包含起始與結束點。",
    initial: { points: "8" },
  },
};

export const SCHEDULE_MODE_LABELS = Object.values(SCHEDULE_MODE_META).map(({ label }) => label);

export const SCHEDULE_STATUS_LABELS = {
  idle: "待命",
  running: "執行中",
  paused: "已暫停",
  stopping: "停止中",
  stopped: "待命",
  completed: "已完成",
  failed: "失敗",
};

export function scheduleModeTypeFromLabel(label) {
  return Object.entries(SCHEDULE_MODE_META).find(([, meta]) => meta.label === label)?.[0] || "seconds_interval";
}

export function buildSchedulePayload(schedule) {
  function positiveNumber(value, label) {
    const parsed = Number(value);
    if (!Number.isFinite(parsed) || parsed <= 0) throw new Error(`${label}必須大於 0。`);
    return parsed;
  }

  const payload = {
    duration_seconds: Number(schedule.duration_seconds),
    rotation_start_deg: Number(schedule.rotation_start_deg),
    rotation_end_deg: Number(schedule.rotation_end_deg),
    rotation_step_deg: Number(schedule.rotation_step_deg),
    angle_tolerance_deg: Number(schedule.angle_tolerance_deg),
    modes: schedule.modes.map((mode) => {
      if (mode.type === "specific_angles") {
        const parts = mode.angles.split(",").map((value) => value.trim()).filter(Boolean);
        const angles = parts.map(Number);
        if (!angles.length || angles.some((value) => !Number.isFinite(value))) {
          throw new Error("特定角度請使用逗號分隔的有效數字。");
        }
        return { id: mode.id, type: mode.type, angles };
      }
      if (mode.type === "seconds_interval") {
        return { id: mode.id, type: mode.type, interval_seconds: positiveNumber(mode.interval_seconds, "時間間隔") };
      }
      if (mode.type === "angle_interval") {
        return { id: mode.id, type: mode.type, interval_degrees: positiveNumber(mode.interval_degrees, "角度間隔") };
      }
      const points = positiveNumber(mode.points, "等分點數");
      if (!Number.isInteger(points) || points < 2) throw new Error("等分點數必須是至少 2 的整數。");
      return { id: mode.id, type: mode.type, points };
    }),
  };

  const invalidCommon = Object.entries(payload)
    .filter(([key]) => key !== "modes")
    .some(([, value]) => !Number.isFinite(value));
  if (invalidCommon) throw new Error("排程共用控制必須是有效數字。");
  if (payload.duration_seconds <= 0 || payload.rotation_step_deg <= 0 || payload.angle_tolerance_deg < 0) {
    throw new Error("總時長與步進度數必須大於 0，角度誤差不可小於 0。");
  }
  if (payload.rotation_end_deg < payload.rotation_start_deg) {
    throw new Error("結束角度不可小於起始角度。");
  }
  if (!payload.modes.length) throw new Error("請至少新增一個擷取模式。");
  return payload;
}

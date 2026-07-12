export const SCHEDULE_COMMON_DEFAULTS = {
  duration_seconds: "14400",
  rotation_start_deg: "0",
  rotation_end_deg: "360",
  rotation_step_deg: "1",
  angle_tolerance_deg: "0.5",
};

export const INITIAL_SCHEDULE = {
  duration_seconds: "14400",
  rotation_start_deg: "0",
  rotation_end_deg: "360",
  rotation_step_deg: "1",
  angle_tolerance_deg: "0.5",
  modes: [
    {
      id: "mode-1",
      type: "seconds_interval",
      interval_seconds: "60",
    },
  ],
};

export const SCHEDULE_DURATION_FIELD = [
  "duration_seconds",
  "總時長",
  { unit: "seconds" },
];

export const SCHEDULE_COMMON_FIELDS = [
  [
    "rotation_start_deg",
    "起始角度",
    {
      min: 0,
      max: 360,
      step: 0.1,
      suffix: "度",
    },
  ],
  [
    "rotation_end_deg",
    "結束角度",
    {
      min: 0,
      max: 360,
      step: 0.1,
      suffix: "度",
    },
  ],
  [
    "rotation_step_deg",
    "步進度數",
    {
      min: 0.1,
      max: 360,
      step: 0.1,
      suffix: "度",
    },
  ],
  [
    "angle_tolerance_deg",
    "角度誤差",
    {
      min: 0,
      max: 180,
      step: 0.1,
      suffix: "± 度",
    },
  ],
];

export const SCHEDULE_MODE_META = {
  seconds_interval: {
    label: "時間間隔擷取",
    description: "依設定時間間隔擷取一次。",
    initial: {
      interval_seconds: "60",
    },
  },
  angle_interval: {
    label: "角度間隔擷取",
    description: "從起始角度開始，每隔指定角度擷取一次。",
    initial: {
      interval_degrees: "15",
    },
  },
  specific_angles: {
    label: "特定角度擷取",
    description: "在不同特定角度擷取一次，以逗號分隔，例如：30,45,60,122。",
    initial: {
      angles: "30,45,60,122",
    },
  },
  equal_divisions: {
    label: "等分擷取",
    description: "在起始與結束角度之間，平均等分指定數量的擷取點，包含起始與結束點。",
    initial: {
      points: "8",
    },
  },
};

export const SCHEDULE_MODE_LABELS = [
  "時間間隔擷取",
  "角度間隔擷取",
  "特定角度擷取",
  "等分擷取",
];

export const SCHEDULE_STATUS_LABELS = {
  idle: "待命",
  running: "執行中",
  paused: "已暫停",
  stopping: "停止中",
  stopped: "待命",
  completed: "已完成",
  failed: "失敗",
};

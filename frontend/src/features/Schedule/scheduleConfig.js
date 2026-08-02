export const SCHEDULE_COMMON_DEFAULTS = {
  rotation_enabled: true,
  duration_seconds: "14400",
  total_cycles: "48",
  cycle_interval_seconds: "0",
  rotation_start_deg: "0",
  rotation_end_deg: "355",
  angle_tolerance_deg: "0.5",
  stabilization_delay_ms: "800",
  capture_on_return: true,
  return_to_origin: true,
  arm_height_mm: "",
};

export const INITIAL_SCHEDULE = {
  rotation_enabled: true,
  duration_seconds: "14400",
  total_cycles: "48",
  cycle_interval_seconds: "0",
  rotation_start_deg: "0",
  rotation_end_deg: "355",
  angle_tolerance_deg: "0.5",
  stabilization_delay_ms: "800",
  capture_on_return: true,
  return_to_origin: true,
  arm_height_mm: "",
  modes: [
    {
      id: "mode-1",
      type: "time_interval",
      interval_seconds: "60",
    },
  ],
};

export const SCHEDULE_DURATION_FIELD = [
  "duration_seconds",
  "總時長",
  { unit: "seconds" },
];

export const SCHEDULE_TOTAL_CYCLES_FIELD = [
  "total_cycles",
  "總輪數",
  {
    min: 1,
    max: 100000,
    step: 1,
    suffix: "輪",
  },
];

export const SCHEDULE_CYCLE_INTERVAL_FIELD = [
  "cycle_interval_seconds",
  "每輪間隔",
  {
    unit: "seconds",
    description: "一輪往復完成並回到原點後，等待指定時間再開始下一輪；等待期間不擷取，下一輪會重新計算所有擷取模式。",
  },
];

export const SCHEDULE_STABILIZATION_FIELD = [
  "stabilization_delay_ms",
  "穩定等待",
  {
    unit: "milliseconds",
    description: "旋臂停止後，等待植物晃動減弱再拍攝。",
  },
];

export const SCHEDULE_ARM_HEIGHT_FIELD = [
  "arm_height_mm",
  "旋臂高度",
  {
    min: 0,
    max: 10000,
    step: 0.1,
    suffix: "mm",
    description: "與攝影機設定中的旋臂高度共用同一筆設定。",
  },
];

export const SCHEDULE_COMMON_FIELDS = [
  [
    "rotation_start_deg",
    "起始角度",
    {
      min: 0,
      max: 355,
      step: 0.1,
      suffix: "度",
    },
  ],
  [
    "rotation_end_deg",
    "結束角度",
    {
      min: 0,
      max: 355,
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
  continuous_interval: {
    label: "連續間隔擷取",
    description: "依設定間隔持續擷取，不受旋臂移動或每輪等待影響。",
    initial: {
      interval_seconds: "60",
    },
  },
  time_interval: {
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
  "連續間隔擷取",
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

export const SCHEDULE_STATUS_TONES = {
  idle: "neutral",
  running: "success",
  paused: "warning",
  stopping: "warning",
  stopped: "neutral",
  completed: "success",
  failed: "offline",
};

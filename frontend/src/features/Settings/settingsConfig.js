export const SETTINGS_GROUPS = [
  ["motor", "馬達"],
  ["logging", "系統日誌"],
];

export const SETTINGS_CONFIG = {
  motor: {
    motor: {
      velocity_limit_deg_s: true,
      acceleration_deg_s2: true,
      movement_timeout_seconds: true,
    },
  },
  logging: {
    logging: {
      level: true,
    },
  },
};

export const FIELD_META = {
  acceleration_deg_s2: {
    label: "加速度限制",
    type: "number",
    min: 0.1,
    max: 720,
    step: 0.1,
    suffix: "度/秒²",
  },
  capture_interval_seconds: {
    label: "擷取間隔",
    type: "duration",
    unit: "seconds",
    min: 1,
    max: 86400,
  },
  level: {
    label: "日誌層級",
    type: "select",
    options: ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
  },
  movement_timeout_seconds: {
    label: "移動逾時",
    type: "duration",
    unit: "seconds",
    min: 1,
    max: 300,
    className: "col-span-2",
    description: "超過時間仍未完成移動時中止命令。",
  },
  rotation_enabled: {
    label: "啟用旋轉",
    description: "停用後旋臂保持固定，三個鏡頭仍會進行擷取。",
  },
  rotation_end_deg: {
    label: "旋轉結束角度",
    type: "number",
    min: 0,
    max: 360,
    step: 0.1,
    suffix: "度",
  },
  rotation_start_deg: {
    label: "旋轉起始角度",
    type: "number",
    min: 0,
    max: 360,
    step: 0.1,
    suffix: "度",
  },
  rotation_step_deg: {
    label: "旋轉步進角度",
    type: "number",
    min: 0.1,
    max: 360,
    step: 0.1,
    suffix: "度",
  },
  velocity_limit_deg_s: {
    label: "速度限制",
    type: "number",
    min: 0.1,
    max: 360,
    step: 0.1,
    suffix: "度/秒",
  },
};

export const SECTION_META = {
  motor: {
    movement: {
      title: "移動參數",
      description: "速度、加速度與命令逾時。",
      fieldsClassName: "grid-cols-2",
    },
  },
  logging: {
    root: {
      title: "系統日誌",
    },
  },
};

export const SECTION_ORDER = {
  motor: ["movement"],
  logging: ["root"],
};

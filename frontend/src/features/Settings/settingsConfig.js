export const SETTINGS_GROUPS = [
  ["motor", "馬達"],
  ["schedule", "排程"],
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
  schedule: {
    schedule: {
      stabilization_delay_ms: true,
      capture_on_return: true,
      return_to_origin: true,
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
  capture_on_return: {
    label: "往返皆擷取",
    description: "關閉時，抵達結束角度後會直接回到原點並開始下一輪；開啟時，會依正向相同的步進與擷取配置返回原點，並在回程擷取。",
  },
  capture_interval_seconds: {
    label: "擷取間隔",
    type: "duration",
    unit: "seconds",
    min: 1,
    max: 86400,
  },
  duration_minutes: {
    label: "總時長",
    type: "duration",
    unit: "minutes",
    min: 1,
    max: 10080,
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
  return_to_origin: {
    label: "排程結束後回到原點",
    description: "整個排程完成、停止或失敗後，自動讓旋臂回到原點。",
  },
  rotation_enabled: {
    label: "啟用旋轉",
    description: "停用後只執行固定視角擷取。",
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
  stabilization_delay_ms: {
    label: "穩定等待",
    type: "duration",
    unit: "milliseconds",
    min: 0,
    max: 60000,
    description: "旋臂停止後，等待植物晃動減弱再拍攝。",
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
  schedule: {
    execution: {
      title: "執行行為",
      description: "排程拍攝前後的共用硬體行為。",
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
  schedule: ["execution"],
  logging: ["root"],
};

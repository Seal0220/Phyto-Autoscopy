export const SETTINGS_GROUPS = [
  ["motor", "馬達"],
  ["experiment", "排程"],
  ["logging", "紀錄"],
];

export const SETTINGS_CONFIG = {
  motor: {
    motor: {
      velocity_limit_deg_s: true,
      acceleration_deg_s2: true,
      movement_timeout_seconds: true,
      return_to_origin_after_cycle: true,
      disengage_after_cycle: true,
    },
  },
  experiment: {
    experiment: {
      stabilization_delay_ms: true,
      return_to_origin: true,
      capture_top: true,
      capture_fixed_side: true,
      capture_rotating_arm: true,
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
  capture_fixed_side: {
    label: "擷取固定側視角",
  },
  capture_interval_seconds: {
    label: "擷取間隔",
    type: "duration",
    unit: "seconds",
    min: 1,
    max: 86400,
  },
  capture_rotating_arm: {
    label: "擷取旋臂視角",
  },
  capture_top: {
    label: "擷取頂視角",
  },
  disengage_after_cycle: {
    label: "循環後釋放馬達",
    description: "完成一輪擷取後解除保持扭力。",
  },
  duration_minutes: {
    label: "總時長",
    type: "duration",
    unit: "minutes",
    min: 1,
    max: 10080,
  },
  level: {
    label: "紀錄層級",
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
  return_to_origin_after_cycle: {
    label: "循環後回到原點",
    description: "完成一輪擷取後自動回到原點。",
  },
  return_to_origin: {
    label: "排程結束後回到原點",
    description: "整個排程完成或停止後，自動讓旋臂回到原點。",
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
    behavior: {
      title: "循環結束行為",
      description: "每輪擷取完成後的自動動作。",
    },
  },
  experiment: {
    execution: {
      title: "執行行為",
      description: "排程拍攝前後的共用硬體行為。",
    },
    capture: {
      title: "擷取視角",
      description: "選擇排程預設啟用的相機。",
    },
  },
  logging: {
    root: {
      title: "紀錄",
    },
  },
};

export const SECTION_ORDER = {
  motor: ["movement", "behavior"],
  experiment: ["execution", "capture"],
  logging: ["root"],
};

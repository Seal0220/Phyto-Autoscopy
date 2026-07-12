export const SETTINGS_GROUPS = [
  ["cameras", "相機"],
  ["motor", "馬達"],
  ["experiment", "排程"],
  ["logging", "紀錄"],
];

// Strict allow-list: newly added backend fields remain hidden until they are
// deliberately reviewed here. The full original JSON is still retained on save.
const SETTINGS_CONFIG = {
  cameras: {
    cameras: {
      top: {
        enabled: true,
        device_index: true,
        preview_fps: true,
        capture_fps: true,
        width: true,
        height: true,
        jpeg_quality: true,
      },
      fixed_side: {
        enabled: true,
        device_index: true,
        preview_fps: true,
        capture_fps: true,
        width: true,
        height: true,
        jpeg_quality: true,
      },
      rotating_arm: {
        enabled: true,
        device_index: true,
        preview_fps: true,
        capture_fps: true,
        width: true,
        height: true,
        jpeg_quality: true,
      },
    },
  },
  motor: {
    motor: {
      velocity_limit_deg_s: true,
      acceleration_deg_s2: true,
      movement_timeout_seconds: true,
      origin_deg: true,
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

const FIELD_META = {
  acceleration_deg_s2: { label: "加速度限制", type: "number", min: 0.1, max: 720, step: 0.1, suffix: "度/秒²" },
  capture_fixed_side: { label: "擷取固定側視角" },
  capture_fps: { label: "擷取 FPS", type: "number", min: 1, max: 60, step: 1 },
  capture_interval_seconds: { label: "擷取間隔", type: "duration", unit: "seconds", min: 1, max: 86400 },
  capture_rotating_arm: { label: "擷取旋臂視角" },
  capture_top: { label: "擷取頂視角" },
  device_index: { label: "裝置索引", type: "number", min: 0, max: 32, step: 1, description: "對應作業系統辨識到的相機編號。" },
  disengage_after_cycle: { label: "循環後釋放馬達", description: "完成一輪擷取後解除保持扭力。" },
  duration_minutes: { label: "總時長", type: "duration", unit: "minutes", min: 1, max: 10080 },
  enabled: { label: "啟用" },
  height: { label: "影像高度", type: "number", min: 240, max: 4320, step: 1, suffix: "px" },
  jpeg_quality: { label: "JPEG 品質", type: "number", min: 1, max: 100, step: 1, suffix: "%", description: "數值越高，影像品質與檔案大小越高。" },
  level: { label: "紀錄層級", type: "select", options: ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] },
  movement_timeout_seconds: { label: "移動逾時", type: "duration", unit: "seconds", min: 1, max: 300, description: "超過時間仍未完成移動時中止命令。" },
  origin_deg: { label: "原點角度", type: "number", min: 0, max: 360, step: 0.1, suffix: "度" },
  preview_fps: { label: "預覽 FPS", type: "number", min: 1, max: 60, step: 1, description: "只影響即時預覽的更新頻率。" },
  return_to_origin_after_cycle: { label: "循環後回到原點", description: "完成一輪擷取後自動回到原點。" },
  return_to_origin: { label: "排程結束後回到原點", description: "整個排程完成或停止後，自動讓旋臂回到原點。" },
  rotation_enabled: { label: "啟用旋轉", description: "停用後只執行固定視角擷取。" },
  rotation_end_deg: { label: "旋轉結束角度", type: "number", min: 0, max: 360, step: 0.1, suffix: "度" },
  rotation_start_deg: { label: "旋轉起始角度", type: "number", min: 0, max: 360, step: 0.1, suffix: "度" },
  rotation_step_deg: { label: "旋轉步進角度", type: "number", min: 0.1, max: 360, step: 0.1, suffix: "度" },
  stabilization_delay_ms: { label: "穩定等待", type: "duration", unit: "milliseconds", min: 0, max: 60000, description: "旋臂停止後，等待植物晃動減弱再拍攝。" },
  velocity_limit_deg_s: { label: "速度限制", type: "number", min: 0.1, max: 360, step: 0.1, suffix: "度/秒" },
  width: { label: "影像寬度", type: "number", min: 320, max: 7680, step: 1, suffix: "px" },
};

const SECTION_META = {
  cameras: {
    top: { title: "頂視角" },
    fixed_side: { title: "固定側視角" },
    rotating_arm: { title: "旋臂視角" },
  },
  motor: {
    movement: { title: "移動參數", description: "速度、加速度、位置與命令逾時。" },
    behavior: { title: "循環結束行為", description: "每輪擷取完成後的自動動作。" },
  },
  experiment: {
    execution: { title: "執行行為", description: "排程拍攝前後的共用硬體行為。" },
    capture: { title: "擷取視角", description: "選擇工作階段預設啟用的相機。" },
  },
  logging: {
    root: { title: "紀錄" },
  },
};

const SECTION_ORDER = {
  cameras: ["top", "fixed_side", "rotating_arm"],
  motor: ["movement", "behavior"],
  experiment: ["execution", "capture"],
  logging: ["root"],
};

export function cloneValue(value) {
  if (typeof structuredClone === "function") {
    return structuredClone(value);
  }
  return JSON.parse(JSON.stringify(value));
}

function isPlainObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function collectVisibleLeaves(value, rule, path = [], leaves = []) {
  if (rule === true && !isPlainObject(value)) {
    leaves.push({ path, value });
    return leaves;
  }
  if (!isPlainObject(value) || !isPlainObject(rule)) {
    return leaves;
  }
  for (const [key, childRule] of Object.entries(rule)) {
    if (Object.hasOwn(value, key)) {
      collectVisibleLeaves(value[key], childRule, [...path, key], leaves);
    }
  }
  return leaves;
}

export function visibleSettings(group, payload) {
  return collectVisibleLeaves(payload, SETTINGS_CONFIG[group]);
}

export function fieldMeta(leaf) {
  const key = leaf.path.at(-1);
  return FIELD_META[key] || { label: key.replaceAll("_", " ") };
}

export function setNestedValue(target, path, value) {
  let current = target;
  path.forEach((key, index) => {
    if (index === path.length - 1) {
      current[key] = value;
      return;
    }
    if (!isPlainObject(current[key])) {
      current[key] = {};
    }
    current = current[key];
  });
}

function sectionFor(group, path) {
  const key = path.at(-1);
  if (group === "cameras") {
    return path[1] || "top";
  }
  if (group === "motor") {
    return ["return_to_origin_after_cycle", "disengage_after_cycle"].includes(key)
      ? "behavior"
      : "movement";
  }
  if (group === "experiment") {
    if (["capture_top", "capture_fixed_side", "capture_rotating_arm"].includes(key)) {
      return "capture";
    }
    return "execution";
  }
  return "root";
}

export function groupedVisibleSettings(group, payload) {
  const grouped = new Map();
  for (const leaf of visibleSettings(group, payload)) {
    const section = sectionFor(group, leaf.path);
    const current = grouped.get(section) || [];
    current.push(leaf);
    grouped.set(section, current);
  }
  return SECTION_ORDER[group]
    .map((section) => ({ section, leaves: grouped.get(section) || [] }))
    .filter(({ leaves }) => leaves.length > 0);
}

export function sectionMeta(group, section) {
  return SECTION_META[group]?.[section] || { title: section.replaceAll("_", " ") };
}

export function serializeSettingsPayload(group, payload) {
  const next = cloneValue(payload);
  for (const leaf of visibleSettings(group, next)) {
    const meta = fieldMeta(leaf);
    if (["number", "duration"].includes(meta.type)) {
      const number = Number(leaf.value);
      if (!Number.isFinite(number)) {
        throw new Error(`${meta.label} 必須是有效數字。`);
      }
      if (meta.min !== undefined && number < meta.min) {
        throw new Error(`${meta.label} 不可小於 ${meta.min}。`);
      }
      if (meta.max !== undefined && number > meta.max) {
        throw new Error(`${meta.label} 不可大於 ${meta.max}。`);
      }
      setNestedValue(next, leaf.path, number);
    }
  }
  return next;
}

export const IMAGE_PREVIEW_META = {
  top: {
    label: "俯視角",
    device: "CHLOROCULUS EYE-TOP",
  },
  side: {
    label: "側視角",
    device: "CHLOROCULUS EYE-SIDE",
  },
  rotating: {
    label: "旋臂視角",
    device: "CHLOROCULUS EYE-ARM",
  },
};

export const IMAGE_PREVIEW_ORDER = [
  "top",
  "side",
  "rotating",
];

export const IMAGE_PREVIEW_SETTINGS_CONFIG = {
  cameras: {
    top: {
      enabled: true,
      device_index: true,
      preview_fps: true,
      capture_fps: true,
      width: true,
      height: true,
      jpeg_quality: true,
      installation_height_mm: true,
      horizontal_distance_to_origin_mm: true,
    },
    side: {
      enabled: true,
      device_index: true,
      preview_fps: true,
      capture_fps: true,
      width: true,
      height: true,
      jpeg_quality: true,
      installation_height_mm: true,
      horizontal_distance_to_origin_mm: true,
    },
    rotating: {
      enabled: true,
      device_index: true,
      preview_fps: true,
      capture_fps: true,
      width: true,
      height: true,
      jpeg_quality: true,
      arm_height_mm: true,
      horizontal_distance_to_origin_mm: true,
    },
  },
};

export const IMAGE_PREVIEW_FIELD_META = {
  enabled: {
    label: "啟用",
  },
  device_index: {
    label: "裝置索引",
    type: "select",
    valueType: "number",
    min: 0,
    max: 63,
    description: "選擇作業系統辨識到的相機裝置。",
  },
  preview_fps: {
    label: "預覽 FPS",
    type: "number",
    min: 1,
    max: 60,
    step: 1,
    description: "只影響即時預覽的更新頻率。",
  },
  capture_fps: {
    label: "擷取 FPS",
    type: "number",
    min: 1,
    max: 60,
    step: 1,
    description: "相機擷取時要求的幀率；實際可用值與上限依鏡頭及驅動而定。",
  },
  width: {
    label: "影像寬度",
    type: "number",
    min: 320,
    max: 7680,
    step: 1,
    suffix: "px",
  },
  height: {
    label: "影像高度",
    type: "number",
    min: 240,
    max: 4320,
    step: 1,
    suffix: "px",
  },
  jpeg_quality: {
    label: "JPEG 品質",
    type: "number",
    min: 1,
    max: 100,
    step: 1,
    suffix: "%",
    description: "數值越高，影像品質與檔案大小越高。",
  },
  installation_height_mm: {
    label: "安裝高度",
    type: "number",
    min: 0,
    max: 10000,
    step: 0.1,
    suffix: "mm",
    optional: true,
    group: "installation",
  },
  horizontal_distance_to_origin_mm: {
    label: "至原點水平距離",
    type: "number",
    min: 0,
    max: 10000,
    step: 0.1,
    suffix: "mm",
    optional: true,
    group: "installation",
  },
  arm_height_mm: {
    label: "旋臂高度",
    type: "number",
    min: 0,
    max: 10000,
    step: 0.1,
    suffix: "mm",
    optional: true,
    group: "installation",
    description: "此數值與排程通用配置共用。",
  },
};

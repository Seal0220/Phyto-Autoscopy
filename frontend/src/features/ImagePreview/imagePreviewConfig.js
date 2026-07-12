export const IMAGE_PREVIEW_META = {
  top: {
    label: "頂視角",
    device: "CHLOROCULUS EYE-TOP",
  },
  fixed_side: {
    label: "固定側視角",
    device: "CHLOROCULUS EYE-SIDE",
  },
  rotating_arm: {
    label: "旋臂視角",
    device: "CHLOROCULUS EYE-ARM",
  },
};

export const IMAGE_PREVIEW_ORDER = [
  "top",
  "fixed_side",
  "rotating_arm",
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
};

export const IMAGE_PREVIEW_FIELD_META = {
  enabled: {
    label: "啟用",
  },
  device_index: {
    label: "裝置索引",
    type: "number",
    min: 0,
    max: 32,
    step: 1,
    description: "對應作業系統辨識到的相機編號。",
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
    label: "真實 FPS",
    type: "number",
    min: 1,
    max: 60,
    step: 1,
    description: "真實 FPS 為實際擷取影像的每秒張數；實際可用上限依攝影鏡頭而定。",
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
};

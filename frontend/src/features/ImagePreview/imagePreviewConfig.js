export const IMAGE_PREVIEW_META = {
  top: {
    label: "頂視角",
    device: "CHLOROCULUS EYE-TOP",
  },
  side: {
    label: "固定側視角",
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
    },
    side: {
      enabled: true,
      device_index: true,
      preview_fps: true,
      capture_fps: true,
      width: true,
      height: true,
      jpeg_quality: true,
    },
    rotating: {
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
};

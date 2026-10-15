export const TRAJECTORY_POINT_OUTLINE = {
  color: "#07110d",
  width: 1.5,
};

export const TRAJECTORY_DETECTION_LABELS = {
  measured: "實際量測",
  estimated: "模型估計",
  interpolated: "插值",
  manual: "人工修正",
  invalid: "無效",
};

export const TRAJECTORY_ROTATION_LABELS = {
  clockwise: "順時針",
  counterclockwise: "逆時針",
  stationary: "無明顯旋轉",
};

export const TRAJECTORY_PLOT_CONFIG = {
  displaylogo: false,
  // Container resizing is handled by the plot hook's ResizeObserver.
  responsive: false,
  scrollZoom: true,
  toImageButtonOptions: {
    format: "png",
    filename: "phyto-trajectory-3d",
    scale: 2,
  },
};

export const TRAJECTORY_PLAYBACK_INTERVAL_MS = 1000;
export const TRAJECTORY_MODEL_LIMITS = {
  overlayGaussians: 2_000_000,
  cachedModels: 3,
  cachedBytes: 64 * 1024 * 1024,
  downloadTimeoutMs: 60_000,
};

export const TRAJECTORY_METRICS = [
  { key: "z_mm", label: "尖端高度", unit: "mm", digits: 2 },
  { key: "horizontal_displacement_mm", label: "水平位移", unit: "mm", digits: 2 },
  { key: "speed_mm_per_second", label: "移動速度", unit: "mm/s", digits: 3 },
  { key: "confidence", label: "尖端標記信心", unit: "%", digits: 1, scale: 100 },
];

export const TRAJECTORY_METRIC_CHART = {
  width: 720,
  height: 280,
  padding: { top: 18, right: 16, bottom: 78, left: 58 },
  gridSteps: [0, 0.25, 0.5, 0.75, 1],
  tickSize: 9,
  secondsSize: 8,
  axisTitleSize: 10,
};

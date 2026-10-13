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

import { TRAJECTORY_POINT_OUTLINE } from "../trajectoryViewerConfig";

const AXIS_STYLE = {
  showbackground: true,
  backgroundcolor: "#0b1a14",
  gridcolor: "rgba(255,255,255,0.15)",
  linecolor: "#a3a3a3",
  tickcolor: "#a3a3a3",
  tickfont: { color: "#a3a3a3", size: 9 },
  zerolinecolor: "rgba(110,231,183,0.55)",
};

export function trajectoryFrameTrace(ranges) {
  // Fully transparent anchors keep Plotly's data-space transform finite even
  // when both measured lines and points are switched off. No hover or legend.
  return {
    uid: "trajectory-frame-bounds",
    type: "scatter3d",
    mode: "markers",
    x: ranges.x,
    y: ranges.y,
    z: ranges.z,
    opacity: 0,
    marker: { opacity: 0, size: 1, line: { ...TRAJECTORY_POINT_OUTLINE } },
    showlegend: false,
    hoverinfo: "skip",
  };
}

export function defaultTrajectoryCamera() {
  return {
    eye: { x: 1.55, y: 1.55, z: 1.15 },
    up: { x: 0, y: 0, z: 1 },
    center: { x: 0, y: 0, z: 0 },
  };
}

export function currentTrajectoryCamera(
  plotElement,
  fallback,
) {
  // Plotly 3D can emit a wheel event before saving the resulting zoom to its
  // layout. Snapshot the rendered camera, not the previous event's camera.
  const scene = plotElement?._fullLayout?.scene?._scene;
  if (typeof scene?.getCamera !== "function") return fallback;
  try {
    const camera = scene.getCamera();
    const vectors = ["eye", "up", "center"];
    if (!vectors.every((vector) => ["x", "y", "z"].every((axis) => Number.isFinite(camera?.[vector]?.[axis])))) {
      return fallback;
    }
    return structuredClone(camera);
  } catch {
    return fallback;
  }
}

export function formalTrajectoryPlotLayout(
  ranges,
  camera,
  analysisId,
) {
  const revision = `trajectory-camera:${analysisId || "current"}`;
  return {
    autosize: true,
    paper_bgcolor: "rgba(0,0,0,0)",
    plot_bgcolor: "rgba(0,0,0,0)",
    font: { color: "#e5e5e5", size: 12 },
    margin: { l: 0, r: 0, t: 8, b: 72 },
    showlegend: true,
    legend: {
      orientation: "h",
      x: 0,
      y: -0.04,
      yanchor: "top",
      font: { color: "#d4d4d4", size: 11 },
      bgcolor: "rgba(0,0,0,0)",
    },
    scene: {
      bgcolor: "rgba(0,0,0,0)",
      aspectmode: "cube",
      camera,
      uirevision: revision,
      ...Object.fromEntries(["x", "y", "z"].map((axis) => [
        `${axis}axis`,
        { ...AXIS_STYLE, title: { text: `${axis.toUpperCase()}（mm）`, font: { size: 10 } }, range: ranges[axis], autorange: false },
      ])),
    },
    uirevision: revision,
  };
}

import { TRAJECTORY_POINT_OUTLINE } from "../trajectoryViewerConfig";

export const FORMAL_TRAJECTORY_MODE_COLORS = [
  "#6ee7b7",
  "#fde68a",
  "#fda4af",
  "#93c5fd",
  "#c4b5fd",
  "#fdba74",
];

export function formalTrajectoryModeColors(trajectory) {
  const modes = [...new Set(
    (trajectory || [])
      .map((item) => item?.mode_id)
      .filter(Boolean),
  )];

  return Object.fromEntries(
    modes.map((modeId, index) => [
      modeId,
      FORMAL_TRAJECTORY_MODE_COLORS[
        index % FORMAL_TRAJECTORY_MODE_COLORS.length
      ],
    ]),
  );
}

export function finiteTrajectoryPoint(point) {
  return point?.valid === true
    && [point.x_mm, point.y_mm, point.z_mm].every((value) => (
      value !== null
      && value !== undefined
      && value !== ""
      && Number.isFinite(Number(value))
    ));
}

export function formalTrajectoryRanges(trajectory) {
  const bounds = { x: [0, 0], y: [0, 0], z: [0, 0] };
  for (const point of trajectory || []) {
    if (!point?.mode_id || !finiteTrajectoryPoint(point)) continue;
    for (const axis of Object.keys(bounds)) {
      const value = Number(point[`${axis}_mm`]);
      bounds[axis][0] = Math.min(bounds[axis][0], value);
      bounds[axis][1] = Math.max(bounds[axis][1], value);
    }
  }
  // Include the world origin, use equal millimetre scales, and keep every
  // measured point away from the frame even for a nearly vertical trajectory.
  const span = Math.max(1, ...Object.values(bounds).map(([lower, upper]) => upper - lower));
  const halfSpan = span * 0.65;
  return Object.fromEntries(Object.entries(bounds).map(([axis, [lower, upper]]) => {
    const center = (lower + upper) / 2;
    return [axis, [center - halfSpan, center + halfSpan]];
  }));
}

function pointDetails(point) {
  const confidence = Number(point.confidence);
  return [
    point.mode_id,
    point.round_id || "—",
    point.timestamp || "—",
    Number.isFinite(confidence) ? `${(confidence * 100).toFixed(1)}%` : "—",
    point.manually_corrected ? "人工修正" : "自動標記",
  ];
}

export function buildFormalTrajectoryPlot(
  trajectory,
  { showLines = true, showPoints = true, modeColors } = {},
) {
  const colorByMode = modeColors || formalTrajectoryModeColors(trajectory);
  const traces = [];
  let validCount = 0;

  for (const [modeId, color] of Object.entries(colorByMode)) {
    const ordered = trajectory
      .filter((point) => point.mode_id === modeId)
      .sort((left, right) => left.point_index - right.point_index);
    const x = [];
    const y = [];
    const z = [];
    const customdata = [];
    const markerColors = [];
    const markerSizes = [];
    const markerSymbols = [];
    let previousValidIndex = null;
    let firstIndex = null;
    let lastIndex = null;

    const appendGap = () => {
      if (!x.length || x.at(-1) === null) return;
      x.push(null);
      y.push(null);
      z.push(null);
      customdata.push(null);
      markerColors.push(color);
      markerSizes.push(3);
      markerSymbols.push("circle");
    };

    for (const point of ordered) {
      if (!finiteTrajectoryPoint(point)) {
        appendGap();
        previousValidIndex = null;
        continue;
      }
      if (
        previousValidIndex !== null
        && (
          point.missing_segment
          || point.point_index !== previousValidIndex + 1
        )
      ) {
        appendGap();
      }

      const coordinates = [
        Number(point.x_mm),
        Number(point.y_mm),
        Number(point.z_mm),
      ];
      x.push(coordinates[0]);
      y.push(coordinates[1]);
      z.push(coordinates[2]);
      customdata.push(pointDetails(point));
      markerColors.push(point.manually_corrected ? "#ffffff" : color);
      markerSizes.push(point.manually_corrected ? 7 : 4);
      markerSymbols.push("circle");
      previousValidIndex = point.point_index;
      firstIndex ??= x.length - 1;
      lastIndex = x.length - 1;
      validCount += 1;
    }

    if (firstIndex === null) continue;
    markerSizes[firstIndex] = 10;
    markerSymbols[firstIndex] = "circle-open";
    if (lastIndex !== firstIndex) markerSizes[lastIndex] = 10;
    traces.push({
      uid: `trajectory-mode:${modeId}`,
      type: "scatter3d",
      mode: showLines && showPoints ? "lines+markers" : showLines ? "lines" : "markers",
      visible: showLines || showPoints,
      name: modeId,
      x,
      y,
      z,
      customdata,
      connectgaps: false,
      line: { color, width: 4 },
      marker: {
        color: markerColors,
        size: markerSizes,
        symbol: markerSymbols,
        line: { ...TRAJECTORY_POINT_OUTLINE },
      },
      hovertemplate: "模式 %{customdata[0]}<br>輪次 %{customdata[1]}<br>時間 %{customdata[2]}<br>X %{x:.3f} mm<br>Y %{y:.3f} mm<br>Z %{z:.3f} mm<br>信心 %{customdata[3]}・%{customdata[4]}<extra></extra>",
    });
  }

  if (validCount) {
    traces.push({
      uid: "trajectory-world-origin",
      type: "scatter3d",
      mode: "markers",
      visible: showPoints,
      name: "世界原點",
      x: [0],
      y: [0],
      z: [0],
      marker: {
        color: "#ffffff",
        size: 7,
        symbol: "diamond",
        line: { ...TRAJECTORY_POINT_OUTLINE },
      },
      hovertemplate: "世界原點・X 0 / Y 0 / Z 0 mm<extra></extra>",
    });
  }

  return { traces, validCount };
}

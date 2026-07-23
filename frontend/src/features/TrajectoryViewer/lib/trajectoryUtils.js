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

function bounds(values) {
  const minimum = Math.min(...values);
  const maximum = Math.max(...values);

  return {
    minimum,
    span: Math.max(maximum - minimum, 1),
  };
}

export function projectWorldTrajectory(
  trajectory,
  markers,
  {
    yawDegrees = 35,
    pitchDegrees = 25,
    width = 760,
    height = 500,
    padding = 42,
  } = {},
) {
  const yaw = yawDegrees * Math.PI / 180;
  const pitch = pitchDegrees * Math.PI / 180;
  const rotate = (point) => {
    const horizontal = Math.cos(yaw) * point[0]
      - Math.sin(yaw) * point[1];
    const depth = Math.sin(yaw) * point[0]
      + Math.cos(yaw) * point[1];

    return {
      horizontal,
      vertical: Math.cos(pitch) * point[2]
        - Math.sin(pitch) * depth,
      depth: Math.sin(pitch) * point[2]
        + Math.cos(pitch) * depth,
    };
  };
  const trajectoryRotated = trajectory.map((point) => ({
    ...point,
    rotated: rotate([point.x, point.y, point.z]),
  }));
  const markerRotated = (markers || [])
    .filter((marker) => (
      Array.isArray(marker.point)
      && marker.point.every(Number.isFinite)
    ))
    .map((marker) => ({
      ...marker,
      rotated: rotate(marker.point),
    }));
  const combined = [
    ...trajectoryRotated.map((point) => point.rotated),
    ...markerRotated.map((marker) => marker.rotated),
  ];

  if (combined.length === 0) {
    return {
      points: [],
      markers: [],
    };
  }

  const horizontalBounds = bounds(
    combined.map((point) => point.horizontal),
  );
  const verticalBounds = bounds(
    combined.map((point) => point.vertical),
  );
  const project = (point) => ({
    plotX: padding + (
      (point.horizontal - horizontalBounds.minimum)
      / horizontalBounds.span
    ) * (width - padding * 2),
    plotY: height - padding - (
      (point.vertical - verticalBounds.minimum)
      / verticalBounds.span
    ) * (height - padding * 2),
  });

  return {
    points: trajectoryRotated.map((point) => ({
      ...point,
      ...project(point.rotated),
    })),
    markers: markerRotated.map((marker) => ({
      ...marker,
      ...project(marker.rotated),
    })),
  };
}

export function trajectoryPolyline(points) {
  return points
    .map((point) => `${point.plotX},${point.plotY}`)
    .join(" ");
}

export const DETECTION_CATEGORIES = [
  "Automatic",
  "Estimated",
  "Interpolated",
  "Manual",
  "Missing",
  "Invalid",
];

export const DETECTION_META = {
  Automatic: {
    label: "自動",
    color: "#34d399",
  },
  Estimated: {
    label: "估計",
    color: "#fbbf24",
  },
  Interpolated: {
    label: "插值",
    color: "#a3a3a3",
  },
  Manual: {
    label: "人工",
    color: "#ffffff",
  },
  Missing: {
    label: "缺失",
    color: "#737373",
  },
  Invalid: {
    label: "無效",
    color: "#fb7185",
  },
};

function finiteNumber(
  value,
  fallback = null,
) {
  if (value === null || value === undefined || value === "") return fallback;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function detectionType(value) {
  return DETECTION_META[value] ? value : "Missing";
}

export function normalizeTrajectory(payload) {
  const items = Array.isArray(payload) ? payload : [];
  return items.map((item) => ({
    ...item,
    frameId: finiteNumber(item?.frame_id, 0),
    topX: finiteNumber(item?.top_x_px),
    topY: finiteNumber(item?.top_y_px),
    sideX: finiteNumber(item?.side_x_px),
    sideY: finiteNumber(item?.side_y_px),
    rotatingX: finiteNumber(item?.rotating_x_px),
    rotatingY: finiteNumber(item?.rotating_y_px),
    rotatingAngle: finiteNumber(item?.rotating_angle_deg),
    x: finiteNumber(item?.x_mm),
    y: finiteNumber(item?.y_mm),
    z: finiteNumber(item?.z_mm),
    refinedX: finiteNumber(item?.refined_x_mm),
    refinedY: finiteNumber(item?.refined_y_mm),
    refinedZ: finiteNumber(item?.refined_z_mm),
    rotatingError: finiteNumber(item?.rotating_reprojection_error_px),
    rotatingUsed: item?.rotating_used === true,
    topType: detectionType(item?.top_detection_type),
    sideType: detectionType(item?.side_detection_type),
    topError: finiteNumber(item?.top_reprojection_error_px, 0),
    sideError: finiteNumber(item?.side_reprojection_error_px, 0),
    valid: item?.valid === true,
  })).filter((item) => (
    Number.isInteger(item.frameId)
    && item.frameId > 0
    && item.valid
    && [item.topX, item.topY, item.sideX, item.sideY, item.x, item.y, item.z]
      .every((value) => value !== null)
  )).sort((
    left,
    right,
  ) => left.frameId - right.frameId);
}

function normalizePixelPoint(value) {
  if (!value || typeof value !== "object") return null;
  const x = finiteNumber(value.x_px ?? value.x);
  const y = finiteNumber(value.y_px ?? value.y);
  return x === null || y === null
    ? null
    : { x, y };
}

function normalizePixelPointList(value) {
  return Array.isArray(value)
    ? value.map(normalizePixelPoint).filter(Boolean)
    : [];
}

function normalizeDetectionOverlay(value) {
  const detections = [
    value?.automatic_detection,
    value?.resolved_detection,
    value?.interpolated_detection,
  ].filter((detection) => detection && typeof detection === "object");
  const lineSource = detections.find((detection) => (
    Array.isArray(detection.epipolar_line)
    && detection.epipolar_line.length >= 3
    && detection.epipolar_line.slice(0, 3).every((item) => (
      Number.isFinite(Number(item))
    ))
  ));
  const pathSource = detections.find((detection) => (
    Array.isArray(detection.minimum_path)
    && detection.minimum_path.length > 1
  ));

  return {
    epipolarLine: lineSource
      ? lineSource.epipolar_line.slice(0, 3).map(Number)
      : null,
    minimumPath: normalizePixelPointList(pathSource?.minimum_path),
  };
}

export function normalizeTrajectoryFrameOverlay(payload) {
  const frameId = finiteNumber(payload?.pair?.frame_id);
  return {
    frameId: Number.isInteger(frameId) ? frameId : null,
    top: {
      imageUrl: typeof payload?.top_image_url === "string"
        ? payload.top_image_url
        : "",
      ...normalizeDetectionOverlay(payload?.top_detection),
    },
    side: {
      imageUrl: typeof payload?.side_image_url === "string"
        ? payload.side_image_url
        : "",
      ...normalizeDetectionOverlay(payload?.side_detection),
    },
  };
}

export function normalizeDetectionSummary(payload) {
  const normalized = {
    top: {},
    side: {},
    overall: {},
    reprojection: payload?.reprojection && typeof payload.reprojection === "object"
      ? payload.reprojection
      : {},
  };

  for (const scope of ["top", "side", "overall"]) {
    for (const category of DETECTION_CATEGORIES) {
      const source = payload?.[scope]?.[category] || {};
      normalized[scope][category] = {
        count: Math.max(0, finiteNumber(source.count, 0)),
        ratio: Math.min(1, Math.max(0, finiteNumber(source.ratio, 0))),
      };
    }
  }
  return normalized;
}

function bounds(values) {
  const minimum = Math.min(...values);
  const maximum = Math.max(...values);
  const span = Math.max(maximum - minimum, 1);
  return {
    minimum,
    maximum,
    span,
  };
}

export function projectTrajectory2D(
  trajectory,
  cameraId,
  {
    width = 720,
    height = 420,
    padding = 34,
  } = {},
) {
  const xKey = cameraId === "top" ? "topX" : "sideX";
  const yKey = cameraId === "top" ? "topY" : "sideY";
  const typeKey = cameraId === "top" ? "topType" : "sideType";
  const valid = trajectory.filter((point) => (
    Number.isFinite(point[xKey]) && Number.isFinite(point[yKey])
  ));
  if (valid.length === 0) return [];
  const xBounds = bounds(valid.map((point) => point[xKey]));
  const yBounds = bounds(valid.map((point) => point[yKey]));

  return valid.map((point) => ({
    ...point,
    plotX: padding + (
      (point[xKey] - xBounds.minimum) / xBounds.span
    ) * (width - padding * 2),
    plotY: padding + (
      (point[yKey] - yBounds.minimum) / yBounds.span
    ) * (height - padding * 2),
    detectionType: point[typeKey],
  }));
}

function matrix3(value) {
  return Array.isArray(value)
    && value.length === 3
    && value.every((row) => Array.isArray(row) && row.length === 3)
    ? value.map((row) => row.map(Number))
    : null;
}

function matrix4(value) {
  return Array.isArray(value)
    && value.length === 4
    && value.every((row) => Array.isArray(row) && row.length === 4)
    ? value.map((row) => row.map(Number))
    : null;
}

export function transformWorldPoint(
  point,
  transform,
) {
  const matrix = matrix4(transform);
  if (!matrix || !point?.every(Number.isFinite)) return null;
  const homogeneous = [...point, 1];
  const result = matrix.map((row) => row.reduce(
    (
      sum,
      value,
      index,
    ) => sum + value * homogeneous[index],
    0,
  ));
  if (!Number.isFinite(result[3]) || Math.abs(result[3]) < 1e-12) return null;
  return result.slice(0, 3).map((value) => value / result[3]);
}

export function cameraPositionsFromCalibration(calibration) {
  const rotation = matrix3(calibration?.rotation_matrix);
  const translation = Array.isArray(calibration?.translation_vector)
    ? calibration.translation_vector.flat().slice(0, 3).map(Number)
    : null;
  const transform = calibration?.world_transform_matrix;
  const top = transformWorldPoint([0, 0, 0], transform);
  if (
    !rotation
    || !translation
    || translation.length !== 3
    || !translation.every(Number.isFinite)
  ) {
    return {
      top,
      side: null,
    };
  }

  const sideStereo = [0, 1, 2].map((column) => -(
    rotation[0][column] * translation[0]
    + rotation[1][column] * translation[1]
    + rotation[2][column] * translation[2]
  ));

  return {
    top,
    side: transformWorldPoint(sideStereo, transform),
  };
}

export function analysisImageResolution(
  run,
  calibration,
  cameraId,
) {
  const resolution = run?.parameters
    ?.source_validation
    ?.camera_resolutions
    ?.[cameraId];
  if (Array.isArray(resolution) && resolution.length === 2) {
    const width = Number(resolution[0]);
    const height = Number(resolution[1]);
    if (
      Number.isFinite(width)
      && Number.isFinite(height)
      && width > 0
      && height > 0
    ) {
      return [width, height];
    }
  }

  const width = Number(calibration?.image_width);
  const height = Number(calibration?.image_height);
  return Number.isFinite(width)
    && Number.isFinite(height)
    && width > 0
    && height > 0
    ? [width, height]
    : [0, 0];
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
    const horizontal = Math.cos(yaw) * point[0] - Math.sin(yaw) * point[1];
    const depth = Math.sin(yaw) * point[0] + Math.cos(yaw) * point[1];
    return {
      horizontal,
      vertical: Math.cos(pitch) * point[2] - Math.sin(pitch) * depth,
      depth: Math.sin(pitch) * point[2] + Math.cos(pitch) * depth,
    };
  };
  const trajectoryRotated = trajectory.map((point) => ({
    ...point,
    rotated: rotate([point.x, point.y, point.z]),
  }));
  const markerRotated = (markers || []).filter((marker) => (
    Array.isArray(marker.point) && marker.point.every(Number.isFinite)
  )).map((marker) => ({
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
  const horizontalBounds = bounds(combined.map((point) => point.horizontal));
  const verticalBounds = bounds(combined.map((point) => point.vertical));
  const project = (point) => ({
    plotX: padding + (
      (point.horizontal - horizontalBounds.minimum) / horizontalBounds.span
    ) * (width - padding * 2),
    plotY: height - padding - (
      (point.vertical - verticalBounds.minimum) / verticalBounds.span
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
  return points.map((point) => `${point.plotX},${point.plotY}`).join(" ");
}

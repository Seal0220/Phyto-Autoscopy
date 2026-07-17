import assert from "node:assert/strict";
import test from "node:test";

import {
  analysisImageResolution,
  cameraPositionsFromCalibration,
  normalizeDetectionSummary,
  normalizeTrajectory,
  normalizeTrajectoryFrameOverlay,
  projectTrajectory2D,
  projectWorldTrajectory,
} from "../src/features/TrajectoryViewer/lib/trajectoryUtils.js";

test("result images use per-camera analysis resolution before calibration fallback", () => {
  const run = {
    parameters: {
      source_validation: {
        camera_resolutions: {
          top: [1920, 1080],
          side: [1280, 720],
        },
      },
    },
  };
  const calibration = {
    image_width: 640,
    image_height: 480,
  };

  assert.deepEqual(
    analysisImageResolution(run, calibration, "top"),
    [1920, 1080],
  );
  assert.deepEqual(
    analysisImageResolution(run, calibration, "side"),
    [1280, 720],
  );
  assert.deepEqual(
    analysisImageResolution({}, calibration, "top"),
    [640, 480],
  );
});

const trajectoryPayload = [
  {
    frame_id: 1,
    top_x_px: 10,
    top_y_px: 20,
    side_x_px: 30,
    side_y_px: 40,
    x_mm: 0,
    y_mm: 0,
    z_mm: 0,
    top_detection_type: "Automatic",
    side_detection_type: "Manual",
    top_reprojection_error_px: 2,
    side_reprojection_error_px: 3,
    valid: true,
  },
  {
    frame_id: 2,
    top_x_px: 20,
    top_y_px: 30,
    side_x_px: 40,
    side_y_px: 50,
    x_mm: 4,
    y_mm: 5,
    z_mm: 6,
    top_detection_type: "Interpolated",
    side_detection_type: "Estimated",
    top_reprojection_error_px: 12,
    side_reprojection_error_px: 4,
    valid: true,
  },
];

test("trajectory normalization and 2D projection retain detection types", () => {
  const trajectory = normalizeTrajectory(trajectoryPayload);
  const projected = projectTrajectory2D(trajectory, "top");

  assert.equal(trajectory.length, 2);
  assert.equal(projected[0].detectionType, "Automatic");
  assert.equal(projected[1].detectionType, "Interpolated");
  assert.ok(projected[1].plotX > projected[0].plotX);
});

test("trajectory normalization excludes invalid points and orders frame IDs", () => {
  const trajectory = normalizeTrajectory([
    trajectoryPayload[1],
    {
      ...trajectoryPayload[0],
      frame_id: 3,
      valid: false,
    },
    trajectoryPayload[0],
  ]);

  assert.deepEqual(trajectory.map((point) => point.frameId), [1, 2]);
});

test("result frame overlay preserves side epipolar line and minimum path", () => {
  const overlay = normalizeTrajectoryFrameOverlay({
    pair: {
      frame_id: 2,
    },
    side_image_url: "/api/analysis/a/frames/2/images/side",
    side_detection: {
      automatic_detection: {
        epipolar_line: [0, 1, -25],
        minimum_path: [
          { x_px: 10, y_px: 20 },
          { x_px: 12, y_px: 22 },
        ],
      },
    },
  });

  assert.equal(overlay.frameId, 2);
  assert.deepEqual(overlay.side.epipolarLine, [0, 1, -25]);
  assert.deepEqual(overlay.side.minimumPath, [
    { x: 10, y: 20 },
    { x: 12, y: 22 },
  ]);
});

test("camera centers are derived from R, t, and world transform", () => {
  const positions = cameraPositionsFromCalibration({
    rotation_matrix: [
      [1, 0, 0],
      [0, 1, 0],
      [0, 0, 1],
    ],
    translation_vector: [10, 0, 0],
    world_transform_matrix: [
      [1, 0, 0, 100],
      [0, 1, 0, 20],
      [0, 0, 1, 30],
      [0, 0, 0, 1],
    ],
  });

  assert.deepEqual(positions.top, [100, 20, 30]);
  assert.deepEqual(positions.side, [90, 20, 30]);
});

test("world projection includes trajectory and calibration markers", () => {
  const trajectory = normalizeTrajectory(trajectoryPayload);
  const projected = projectWorldTrajectory(
    trajectory,
    [{ id: "origin", point: [0, 0, 0] }],
  );

  assert.equal(projected.points.length, 2);
  assert.equal(projected.markers.length, 1);
  assert.ok(projected.points.every((point) => Number.isFinite(point.plotX)));
});

test("detection summary fills every required category", () => {
  const summary = normalizeDetectionSummary({
    top: {
      Automatic: { count: 2, ratio: 0.5 },
    },
  });

  assert.equal(summary.top.Automatic.count, 2);
  assert.equal(summary.side.Invalid.count, 0);
  assert.equal(summary.overall.Missing.ratio, 0);
});

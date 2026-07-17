import assert from "node:assert/strict";
import test from "node:test";

import {
  appendStereoPair,
  buildCalibrationCreatePayload,
  calibrationBaselineComparison,
  calibrationPreviewItems,
  calibrationProfilesFromPayload,
  calibrationStatus,
  calibrationWorkflowAvailability,
  calibrationWorkflowStepState,
  createCalibrationDraft,
  distortionNamed,
  isValidCalibrationId,
  parseRigidTransform,
  sourceImagesFromPayload,
  toggleCalibrationPath,
} from "../src/features/Calibration/lib/calibrationUtils.js";

function validDraft() {
  return {
    ...createCalibrationDraft(),
    topImagePaths: ["data/captures/top.png"],
    sideImagePaths: ["data/captures/side.png"],
    stereoImagePairs: [[
      "data/captures/top.png",
      "data/captures/side.png",
    ]],
    squareSizeMmX: "12.5",
    squareSizeMmY: "12.5",
    stereoPatternColumns: "8",
    stereoPatternRows: "6",
    stereoSquareSizeMmX: "20",
    stereoSquareSizeMmY: "20",
    individualBoardWidthCm: "59.4",
    individualBoardHeightCm: "84.1",
    stereoBoardWidthCm: "42.0",
    stereoBoardHeightCm: "59.4",
    worldTransformConfirmed: true,
  };
}

test("calibration defaults do not pretend paper board sizes were measured", () => {
  const draft = createCalibrationDraft();
  assert.equal(draft.individualBoardWidthCm, "");
  assert.equal(draft.individualBoardHeightCm, "");
  assert.equal(draft.stereoBoardWidthCm, "");
  assert.equal(draft.stereoBoardHeightCm, "");
  assert.equal(draft.stereoPatternColumns, "");
  assert.equal(draft.stereoPatternRows, "");
  assert.equal(draft.worldTransformConfirmed, false);
});

test("calibration route IDs reject traversal and unbounded values", () => {
  assert.equal(isValidCalibrationId("calibration_2026-07-17_001"), true);
  assert.equal(isValidCalibrationId("../calibration"), false);
  assert.equal(isValidCalibrationId("校正-1"), false);
  assert.equal(isValidCalibrationId("a".repeat(161)), false);
});

test("calibration create payload requires measured world transform confirmation", () => {
  const draft = validDraft();
  draft.worldTransformConfirmed = false;
  assert.throws(
    () => buildCalibrationCreatePayload(draft),
    /已經實際量測或驗證/,
  );
});

test("calibration create payload preserves every explicit measured field", () => {
  const payload = buildCalibrationCreatePayload(validDraft());
  assert.deepEqual(payload.top_image_paths, ["data/captures/top.png"]);
  assert.deepEqual(payload.side_image_paths, ["data/captures/side.png"]);
  assert.deepEqual(payload.stereo_image_pairs, [[
    "data/captures/top.png",
    "data/captures/side.png",
  ]]);
  assert.equal(payload.pattern_columns, 10);
  assert.equal(payload.pattern_rows, 7);
  assert.equal(payload.square_size_mm_x, 12.5);
  assert.equal(payload.square_size_mm_y, 12.5);
  assert.equal(payload.stereo_pattern_columns, 8);
  assert.equal(payload.stereo_pattern_rows, 6);
  assert.equal(payload.stereo_square_size_mm_x, 20);
  assert.equal(payload.stereo_square_size_mm_y, 20);
  assert.equal(payload.individual_board_width_cm, 59.4);
  assert.equal(payload.individual_board_height_cm, 84.1);
  assert.equal(payload.stereo_board_width_cm, 42);
  assert.equal(payload.stereo_board_height_cm, 59.4);
  assert.deepEqual(payload.world_transform_matrix, [
    [1, 0, 0, 0],
    [0, 1, 0, 0],
    [0, 0, 1, 0],
    [0, 0, 0, 1],
  ]);
});

test("calibration rejects reusing one image as both intrinsic camera roles", () => {
  const draft = validDraft();
  draft.sideImagePaths = [
    "data/captures/top.png",
    "data/captures/side.png",
  ];

  assert.throws(
    () => buildCalibrationCreatePayload(draft),
    /不可同時作為俯視角與側視角/,
  );
});

test("rigid transform rejects scaling and invalid homogeneous row", () => {
  assert.throws(
    () => parseRigidTransform([
      [2, 0, 0, 0],
      [0, 1, 0, 0],
      [0, 0, 1, 0],
      [0, 0, 0, 1],
    ]),
    /正交矩陣/,
  );
  assert.throws(
    () => parseRigidTransform([
      [1, 0, 0, 0],
      [0, 1, 0, 0],
      [0, 0, 1, 0],
      [0, 0, 1, 1],
    ]),
    /最後一列/,
  );
});

test("paper comparison identifies actual board differences without deriving missing values", () => {
  const matching = calibrationBaselineComparison(validDraft());
  assert.deepEqual(matching, {
    individualComplete: true,
    stereoComplete: true,
    patternComplete: true,
    individualMatches: true,
    stereoMatches: true,
    patternMatches: true,
  });
  const changed = validDraft();
  changed.stereoBoardWidthCm = "40";
  changed.patternColumns = "9";
  assert.equal(calibrationBaselineComparison(changed).stereoMatches, false);
  assert.equal(calibrationBaselineComparison(changed).patternMatches, false);
});

test("image selection and explicit stereo pairing remain deterministic", () => {
  assert.deepEqual(toggleCalibrationPath([], "top.png"), ["top.png"]);
  assert.deepEqual(toggleCalibrationPath(["top.png"], "top.png"), []);
  assert.deepEqual(
    appendStereoPair([], "top.png", "side.png"),
    [["top.png", "side.png"]],
  );
  assert.throws(
    () => appendStereoPair(
      [["top.png", "side.png"]],
      "top.png",
      "side.png",
    ),
    /已經加入/,
  );
});

test("payload adapters reject malformed list rows", () => {
  assert.deepEqual(sourceImagesFromPayload([
    {
      path: "a.png",
    },
    null,
    {},
  ]), [{ path: "a.png" }]);
  assert.deepEqual(calibrationProfilesFromPayload({
    profiles: [{ calibration_id: "calibration-1" }],
  }), [{ calibration_id: "calibration-1" }]);
  assert.equal(calibrationStatus("potentially_invalid").label, "可能失效");
});

test("preview adapter includes all individual and stereo views", () => {
  const previews = calibrationPreviewItems({
    corner_detections: {
      top: [{
        image_id: "top.png",
        found: true,
        preview_name: "top.jpg",
      }],
      side: [{
        image_id: "side.png",
        found: false,
        preview_name: "side.jpg",
      }],
      stereo: [{
        pair_id: "pair-1",
        top: {
          image_id: "stereo-top.png",
          found: true,
          preview_name: "stereo-top.jpg",
        },
        side: {
          image_id: "stereo-side.png",
          found: true,
          preview_name: "stereo-side.jpg",
        },
      }],
    },
  });
  assert.equal(previews.length, 4);
  assert.deepEqual(
    previews.map((item) => item.previewName),
    ["top.jpg", "side.jpg", "stereo-top.jpg", "stereo-side.jpg"],
  );
});

test("workflow availability follows persisted outputs instead of status labels", () => {
  const availability = calibrationWorkflowAvailability({
    status: "failed",
    corner_detections: {
      top: [{ found: true }],
      side: [{ found: true }],
      stereo: [{ usable: true }],
    },
    top_camera_matrix: [[1]],
    top_distortion_coefficients: [0],
    side_camera_matrix: [[1]],
    side_distortion_coefficients: [0],
    rotation_matrix: [[1]],
    translation_vector: [1, 0, 0],
    essential_matrix: [[1]],
    fundamental_matrix: [[1]],
    top_projection_matrix: [[1]],
    side_projection_matrix: [[1]],
    disparity_to_depth_matrix: [[1]],
  });
  assert.deepEqual(availability, {
    corners: true,
    intrinsics: true,
    stereo: true,
    rotating: false,
    validate: true,
  });
});

test("workflow labels do not report failed corner arrays as completed", () => {
  const failed = {
    status: "failed",
    corner_detections: {
      top: [{ found: false }],
      side: [{ found: false }],
      stereo: [{ usable: false }],
    },
  };
  assert.equal(
    calibrationWorkflowStepState(failed, "corners"),
    "尚未執行",
  );

  const complete = {
    corner_detections: {
      top: [{ found: true }],
      side: [{ found: true }],
      stereo: [{ usable: true }],
    },
  };
  assert.equal(
    calibrationWorkflowStepState(complete, "corners"),
    "已完成",
  );
});

test("distortion coefficients use OpenCV k1 k2 p1 p2 k3 order", () => {
  assert.deepEqual(distortionNamed([1, 2, 3, 4, 5]), [
    { name: "k1", value: 1 },
    { name: "k2", value: 2 },
    { name: "p1", value: 3 },
    { name: "p2", value: 4 },
    { name: "k3", value: 5 },
  ]);
});

import test from "node:test";
import assert from "node:assert/strict";
import {
  needsStereoPoseReview,
  completedStereoPairs,
  stereoImagePoint,
  stereoPairCheck,
  stereoPairLabel,
  stereoPairsAfterRefresh,
  stereoPairsWithModelPoint,
  stereoPairsWithMovedModelPoint,
  stereoPairsWithoutPair,
  stereoReviewRequest,
  stereoValidationCount,
} from "../src/features/AnalysisRun/lib/analysisStereoReviewUtils.js";
import { gaussianPointIndex, knownModelPoint } from "../src/features/AnalysisRun/lib/analysisModelReferenceUtils.js";
import { analysisRunActionAvailability, analysisRunDisplay } from "../src/features/AnalysisRun/lib/analysisRunUtils.js";

test("stereo review opens for new pending and existing failed runs, and cannot be skipped", () => {
  assert.equal(needsStereoPoseReview({ status: "needs_review", stage: "waiting_for_stereo_review" }), true);
  assert.equal(needsStereoPoseReview({ status: "failed", stage: "estimating_stereo_pose" }), true);
  assert.equal(needsStereoPoseReview({ status: "needs_review", stage: "waiting_for_review" }), false);
  const actions = analysisRunActionAvailability("needs_review", "waiting_for_stereo_review");
  assert.equal(actions.review, true);
  assert.equal(actions.skipReview, false);
  assert.equal(analysisRunActionAvailability("failed", "estimating_stereo_pose").review, true);
  assert.equal(analysisRunDisplay({ stage: "waiting_for_stereo_review" }).stage, "等待人工雙鏡頭配對");
});

test("model registration requires four complete 3D references and stays in review", () => {
  const viewIds = [{ camera_id: "top", view_id: "t" }, { camera_id: "side", view_id: "s" }];
  const point = { x_px: 10, y_px: 20 };
  const pairs = Array.from({ length: 4 }, (_, id) => ({ model_point_id: id, top: point, side: point }));
  const incomplete = { top: point, side: point };
  assert.equal(needsStereoPoseReview({ status: "needs_review", stage: "waiting_for_model_review" }), true);
  assert.equal(analysisRunActionAvailability("needs_review", "waiting_for_model_review").skipReview, false);
  assert.equal(analysisRunDisplay({ stage: "waiting_for_model_review" }).stage, "等待人工對齊模型");
  assert.equal(completedStereoPairs([...pairs, incomplete], true).length, 4);
  assert.deepEqual(stereoReviewRequest(viewIds, [...pairs, incomplete], { signature: "model-v1" }), {
    top_view_id: "t", side_view_id: "s", correspondences: pairs, reference_signature: "model-v1",
  });
});

test("render picking retains Gaussian vertex IDs and existing sparse anchors", () => {
  const reference = {
    points: [{ id: 423, xyz: [1, 2, 3], rgb: [40, 80, 60] }, { id: 11, xyz: [2, 3, 4], rgb: [20, 10, 0] }],
    orbit: { center: [0, 0, 0], direction: [0, 0, 1], radius: 20 },
    center: [1, 2, 3], radius: 2, gaussian_point_offset: 424, gaussian_count: 200000,
  };
  assert.equal(gaussianPointIndex(reference, 424), 0);
  assert.equal(gaussianPointIndex(reference, 200423), 199999);
  assert.equal(gaussianPointIndex(reference, 200424), null);
  assert.equal(gaussianPointIndex(reference, 423), null);
  assert.equal(knownModelPoint(reference, 423), true);
  assert.equal(knownModelPoint(reference, 424), true);
  assert.equal(knownModelPoint(reference, 12), false);
  assert.equal(knownModelPoint(reference, NaN), false);
});

test("a refreshed model never silently reuses stale Gaussian IDs", () => {
  const pairs = [{ model_point_id: 100, top: { x_px: 10, y_px: 20 }, side: { x_px: 30, y_px: 40 } }];
  const previous = { views: [{ view_id: "t" }, { view_id: "s" }], reference: { signature: "old" } };
  assert.equal(stereoPairsAfterRefresh(pairs, previous, previous), pairs);
  const changed = { ...previous, reference: { signature: "new" } };
  assert.deepEqual(stereoPairsAfterRefresh(pairs, previous, changed), [{ top: pairs[0].top, side: pairs[0].side }]);
  assert.equal(stereoPairsAfterRefresh(pairs, previous, { ...changed, draft: { correspondences: pairs } }), pairs);
  assert.deepEqual(stereoPairsAfterRefresh(pairs, previous, { ...changed, views: [{ view_id: "other" }] }), [{ top: null, side: null }]);
});

test("picking a new model anchor adds a pair without overwriting previous image marks", () => {
  const first = stereoPairsWithModelPoint([{ top: null, side: null }], 0, 100);
  assert.equal(first.pairs.length, 1);
  assert.equal(first.pairs[0].model_point_id, 100);
  first.pairs[0].top = { x_px: 10, y_px: 20 };
  first.pairs[0].side = { x_px: 30, y_px: 40 };
  const second = stereoPairsWithModelPoint(first.pairs, 0, 101);
  assert.equal(second.pairs.length, 2);
  assert.equal(second.selected, 1);
  assert.equal(second.pairs[0], first.pairs[0]);
  assert.deepEqual(second.pairs[1], { model_point_id: 101, top: null, side: null });
  assert.deepEqual(stereoPairsWithModelPoint(second.pairs, 1, 100), { pairs: second.pairs, selected: 0 });
  const blank = [...second.pairs, { top: null, side: null }];
  assert.equal(stereoPairsWithModelPoint(blank, 0, 102).selected, 2);
  const full = Array.from({ length: 200 }, (_, id) => ({ model_point_id: id }));
  assert.equal(stereoPairsWithModelPoint(full, 0, 201), null);
});

test("moving an existing model marker preserves its image marks and pair number", () => {
  const pairs = [
    { model_point_id: 100, top: { x_px: 10, y_px: 20 }, side: { x_px: 30, y_px: 40 } },
    { model_point_id: 101, top: null, side: null },
  ];
  const moved = stereoPairsWithMovedModelPoint(pairs, 100, 120);
  assert.equal(moved.selected, 0);
  assert.equal(moved.pairs.length, 2);
  assert.equal(moved.pairs[0].model_point_id, 120);
  assert.equal(moved.pairs[0].top, pairs[0].top);
  assert.equal(moved.pairs[0].side, pairs[0].side);
  assert.equal(moved.pairs[1], pairs[1]);
  assert.equal(pairs[0].model_point_id, 100);
  assert.equal(stereoPairsWithMovedModelPoint(pairs, 100, 101), null);
  assert.equal(stereoPairsWithMovedModelPoint(pairs, 999, 120), null);
  assert.equal(stereoPairsWithMovedModelPoint(pairs, 100, NaN), null);
});

test("removing a specific group keeps the selected correspondence and one editable blank", () => {
  const pairs = [100, 101, 102].map((model_point_id) => ({ model_point_id, top: null, side: null }));
  assert.deepEqual(stereoPairsWithoutPair(pairs, 2, 0), { pairs: pairs.slice(1), selected: 1 });
  assert.deepEqual(stereoPairsWithoutPair(pairs, 0, 2), { pairs: pairs.slice(0, 2), selected: 0 });
  assert.deepEqual(stereoPairsWithoutPair(pairs, 2, 2), { pairs: pairs.slice(0, 2), selected: 1 });
  assert.deepEqual(stereoPairsWithoutPair(pairs, 1, 1), { pairs: [pairs[0], pairs[2]], selected: 1 });
  assert.deepEqual(stereoPairsWithoutPair([pairs[0]], 0, 0), { pairs: [{ top: null, side: null }], selected: 0 });
  assert.deepEqual(stereoPairsWithoutPair(pairs, 1, -1), { pairs, selected: 1 });
});

test("manual point coordinates are exact for resized and fullscreen letterboxed images", () => {
  assert.deepEqual(stereoImagePoint(320, 240, { left: 0, top: 0, width: 640, height: 480 }, 1280, 960), { x_px: 640, y_px: 480 });
  // 1280x960 image displayed in a 1000x500 fullscreen box has side bars.
  assert.deepEqual(stereoImagePoint(500, 250, { left: 0, top: 0, width: 1000, height: 500 }, 1280, 960), { x_px: 640, y_px: 480 });
  assert.equal(stereoImagePoint(50, 250, { left: 0, top: 0, width: 1000, height: 500 }, 1280, 960), null);
});

test("manual submission includes only complete top/side correspondences", () => {
  const top = { x_px: 100, y_px: 200 }, side = { x_px: 300, y_px: 400 };
  assert.deepEqual(stereoReviewRequest([{ camera_id: "side", view_id: "s" }, { camera_id: "top", view_id: "t" }], [{ top, side }, { top: null, side: null }]), {
    top_view_id: "t", side_view_id: "s", correspondences: [{ top, side }],
  });
});

test("submission keeps pair identity when blank rows are removed before validation", () => {
  const pairs = [
    { top: null, side: null },
    { top: { x_px: 100, y_px: 200 }, side: { x_px: 300, y_px: 400 } },
    { top: null, side: null },
    { top: { x_px: 150, y_px: 250 }, side: { x_px: 350, y_px: 450 } },
  ];
  const request = stereoReviewRequest([{ camera_id: "top", view_id: "t" }, { camera_id: "side", view_id: "s" }], pairs);
  assert.equal(request.correspondences.indexOf(pairs[3]), 1);
  assert.equal(request.correspondences[0], pairs[1]);
  assert.equal(stereoPairLabel(request.correspondences[1], 1, { validated_stage: "geometric", inlier_indices: [1] }), "第 2 組（內點）");
});

test("geometry feedback maps sparse inliers to the original pair numbers", () => {
  const validation = { validated_stage: "geometric", inlier_indices: [0, 2, 4, 8] };
  const pair = { top: { x_px: 100, y_px: 200 }, side: { x_px: 300, y_px: 400 } };
  assert.equal(stereoValidationCount(validation), 4);
  assert.equal(stereoPairCheck(validation, 8), "inlier");
  assert.equal(stereoPairCheck(validation, 1), "check");
  assert.equal(stereoPairLabel(pair, 8, validation), "第 9 組（內點）");
  assert.equal(stereoPairLabel(pair, 1, validation), "第 2 組（需檢查）");
  assert.equal(stereoPairLabel({ top: null, side: null }, 1, validation), "第 2 組（待標記）");
});

test("unverified and edited pairs have no stale geometry verdict", () => {
  const pair = { top: { x_px: 100, y_px: 200 }, side: { x_px: 300, y_px: 400 } };
  for (const validation of [null, undefined, {}, { validated_stage: "not_started", inlier_indices: [] }]) {
    assert.equal(stereoValidationCount(validation), null);
    assert.equal(stereoPairCheck(validation, 0), null);
    assert.equal(stereoPairLabel(pair, 0, validation), "第 1 組（已標記）");
  }
  const rejected = { validated_stage: "geometric", inlier_indices: [] };
  assert.equal(stereoValidationCount(rejected), 0);
  assert.equal(stereoPairCheck(rejected, 0), "check");
});

test("camera feedback identifies suspect points without accepting a rejected pose", () => {
  const validation = {
    validated_stage: "reprojection", inlier_indices: [], status: "rejected",
    cameras: {
      top: { status: "rejected", inlier_indices: [0, 1, 2], outlier_indices: [3, 4] },
      side: { status: "accepted", inlier_indices: [0, 1, 2, 3], outlier_indices: [4] },
    },
  };
  const pair = { top: { x_px: 10, y_px: 20 }, side: { x_px: 30, y_px: 40 } };
  assert.equal(stereoValidationCount(validation), 0);
  assert.equal(stereoPairCheck(validation, 0, "top"), null);
  assert.equal(stereoPairCheck(validation, 3, "top"), "check");
  assert.equal(stereoPairCheck(validation, 3, "side"), "inlier");
  assert.equal(stereoPairLabel(pair, 3, validation, "top"), "第 4 組（需檢查）");
  assert.equal(stereoPairLabel(pair, 0, validation, "top"), "第 1 組（已標記）");
  assert.equal(stereoPairCheck({ cameras: { top: { status: "not_solved" } } }, 0, "top"), null);
  assert.equal(stereoPairCheck({ cameras: { top: { status: "ambiguous", inlier_indices: [] } } }, 0, "top"), null);
});

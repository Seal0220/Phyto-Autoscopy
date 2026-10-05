import test from "node:test";
import assert from "node:assert/strict";
import { needsStereoPoseReview, stereoImagePoint, stereoReviewRequest } from "../src/features/AnalysisRun/lib/analysisStereoReviewUtils.js";
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

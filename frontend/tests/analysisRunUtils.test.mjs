import assert from "node:assert/strict";
import test from "node:test";

import {
  analysisInputCount,
  analysisRunActionAvailability,
  analysisRunActionRequest,
  analysisRunDisplay,
  isValidAnalysisId,
  normalizeAnalysisProgress,
  normalizeAnalysisRun,
} from "../src/features/AnalysisRun/lib/analysisRunUtils.js";

test("analysis run normalization clamps progress and preserves metadata", () => {
  const run = normalizeAnalysisRun({
    analysis_id: "analysis-1",
    record_id: "record-1",
    status: "processing",
    progress: 1.5,
    parameters: {
      input_manifest: [{}, {}, {}],
    },
  });

  assert.equal(run.progress, 1);
  assert.equal(run.record_id, "record-1");
  assert.equal(analysisInputCount(run), 3);
  assert.equal(analysisRunDisplay(run).progressPercent, 100);
  assert.equal(normalizeAnalysisProgress({ progress: -1 }).progress, 0);
});

test("analysis route IDs reject path and oversized input", () => {
  assert.equal(isValidAnalysisId("analysis_2026-07-17_001"), true);
  assert.equal(isValidAnalysisId("../analysis"), false);
  assert.equal(isValidAnalysisId("分析-1"), false);
  assert.equal(isValidAnalysisId("a".repeat(161)), false);
});

test("pose finalization shows its own stage and completed work units", () => {
  const checking = analysisRunDisplay({
    status: "processing", stage: "checking_pose_consistency",
    current_frame: 256, total_frames: 51522, progress: 0.32,
  });
  assert.equal(checking.stage, "檢查姿態一致性");
  assert.equal(checking.progressNote, "256 / 51522 筆");
  assert.equal(checking.progressPercent, 32);
  const saving = analysisRunDisplay({
    status: "processing", stage: "saving_camera_poses",
    current_frame: 10, total_frames: 363, progress: 0.32,
  });
  assert.equal(saving.stage, "保存相機姿態");
  assert.equal(saving.progressNote, "10 / 363 輪");
});

test("analysis run actions follow lifecycle status", () => {
  assert.equal(analysisRunActionAvailability("draft").validate, true);
  assert.equal(analysisRunActionAvailability("ready").start, true);
  assert.equal(analysisRunActionAvailability("processing").cancel, true);
  assert.equal(analysisRunActionAvailability("failed").retry, true);
  assert.equal(analysisRunActionAvailability("failed").reset, true);
  assert.equal(analysisRunActionAvailability("failed").resume, false);
  assert.equal(analysisRunActionAvailability("paused").resume, true);
  assert.equal(analysisRunActionAvailability("needs_review").review, true);
  assert.equal(analysisRunActionAvailability("needs_review").skipReview, true);
  assert.equal(analysisRunActionAvailability("reviewing").skipReview, true);
  assert.equal(analysisRunActionAvailability("completed").skipReview, false);
  assert.equal(analysisRunActionAvailability("completed").results, true);
  assert.equal(analysisRunActionAvailability("completed").export, true);
});

test("skip-review action reconstructs with an explicit incomplete-review flag", () => {
  assert.deepEqual(analysisRunActionRequest("reconstruct_without_review"), {
    action: "reconstruct",
    body: {
      manual_review_completed: false,
    },
  });
  assert.deepEqual(analysisRunActionRequest("validate"), {
    action: "validate",
    body: {},
  });
});

test("rebuilding an alignment preview is an explicit action and cannot skip camera review", () => {
  for (const status of ["needs_review", "reviewing"]) {
    const available = analysisRunActionAvailability(status, "waiting_for_model_review");
    assert.equal(available.rebuildPreview, true);
    assert.equal(available.skipReview, false);
    assert.equal(available.resume, false);
    assert.equal(available.review, true);
    assert.equal(analysisRunActionAvailability(status, "waiting_for_stereo_review").rebuildPreview, false);
  }
  assert.equal(analysisRunActionAvailability("processing", "building_alignment_preview").rebuildPreview, false);
  assert.equal(analysisRunDisplay({status: "processing", stage: "building_alignment_preview", current_frame: 20, total_frames: 100}).stage, "建立選點預覽");
});

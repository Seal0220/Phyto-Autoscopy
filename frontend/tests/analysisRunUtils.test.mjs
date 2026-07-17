import assert from "node:assert/strict";
import test from "node:test";

import {
  analysisInputCount,
  analysisRunActionAvailability,
  analysisRunActionRequest,
  analysisRunDisplay,
  framePairCounts,
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

test("analysis run actions follow lifecycle status", () => {
  assert.equal(analysisRunActionAvailability("draft").validate, true);
  assert.equal(analysisRunActionAvailability("ready").start, true);
  assert.equal(analysisRunActionAvailability("processing").cancel, true);
  assert.equal(analysisRunActionAvailability("failed").retry, true);
  assert.equal(analysisRunActionAvailability("failed").reset, true);
  assert.equal("resume" in analysisRunActionAvailability("failed"), false);
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

test("frame pair counts distinguish automatic, manual, and unresolved", () => {
  const counts = framePairCounts([
    { pair_status: "paired" },
    { pair_status: "manually_aligned" },
    { pair_status: "top_missing" },
    { pair_status: "outside_tolerance" },
  ]);

  assert.deepEqual(counts, {
    paired: 1,
    manuallyAligned: 1,
    unresolved: 2,
  });
});

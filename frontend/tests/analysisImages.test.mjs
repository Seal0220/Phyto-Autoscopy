import assert from "node:assert/strict";
import test from "node:test";

import {
  analysisArtifactUrl,
  analysisViewImageUrl,
} from "../src/lib/analysisImageUtils.js";
import {
  analysisImageGroups,
  analysisRunDisplay,
  normalizeAnalysisProgress,
} from "../src/features/AnalysisRun/lib/analysisRunUtils.js";

test("analysis images preserve encoded IDs and Windows artifact paths through the BFF", () => {
  assert.equal(
    analysisViewImageUrl("analysis-1", "mode:round:top", "source"),
    "/api/analysis/analysis-1/views/mode%3Around%3Atop/image?coordinate_space=source",
  );
  assert.equal(
    analysisArtifactUrl("analysis-1", "rounds\\mode 1\\preview.png"),
    "/api/analysis/analysis-1/artifacts/rounds/mode%201/preview.png",
  );
});

test("round gallery keeps each snapshot's three views together", () => {
  const views = [
    { view_id: "top-1", snapshot_id: "snapshot.01", camera_id: "top" },
    { view_id: "side-1", snapshot_id: "snapshot.01", camera_id: "side" },
    { view_id: "rotating-1", snapshot_id: "snapshot.01", camera_id: "rotating" },
    { view_id: "top-2", snapshot_id: "snapshot.02", camera_id: "top" },
  ];
  const groups = analysisImageGroups(views);
  assert.equal(groups.length, 2);
  assert.deepEqual(groups[0].views, views.slice(0, 3));
  assert.deepEqual(analysisImageGroups(null), []);
});

test("socket progress retains failure images and identifies stereo stage", () => {
  const preview = { views: [{ view_id: "top-1" }], diagnostics: { matched_features: 3 } };
  const progress = normalizeAnalysisProgress({
    status: "failed", stage: "estimating_stereo_pose", processing_preview: preview,
  });
  assert.deepEqual(progress.processing_preview, preview);
  assert.equal(analysisRunDisplay(progress).stage, "估算雙鏡頭相對姿態");
  assert.equal(normalizeAnalysisProgress({}).processing_preview, null);
});

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
  analysisRunActionAvailability,
  analysisInputCount,
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

test("analysis pause controls wait for saving and preserve checkpoint progress", () => {
  for (const status of ["validating", "processing", "reconstructing"]) {
    assert.equal(analysisRunActionAvailability(status).pause, true);
  }
  assert.equal(analysisRunActionAvailability("pausing").pause, false);
  assert.equal(analysisRunActionAvailability("pausing").resume, false);
  assert.equal(analysisRunActionAvailability("paused").resume, true);
  const checkpoints = { completed_steps: 42, recent_steps: [{ stage: "undistorting_images", backend: "cuda", item: "view-1" }] };
  const progress = normalizeAnalysisProgress({ status: "paused", checkpoints });
  assert.deepEqual(progress.checkpoints, checkpoints);
  assert.equal(analysisRunDisplay(progress).status.label, "已暫停");
  assert.equal(analysisInputCount({ parameters: { input_count: 1000 } }), 1000);
  const display = analysisRunDisplay({
    image_probe_backends: { cpu: 2, remap_gpu: 2, remap_cpu: 0, reused: 10 },
  });
  assert.equal(display.probeNote, "GPU 去畸變 2 張 · CPU 去畸變 0 張 · 沿用已完成影像 10 張");
  assert.equal(analysisRunDisplay({
    image_probe_backends: { remap_gpu: 0, remap_cpu: 0, reused: 55, reused_gpu: 55, reused_cpu: 0 },
  }).probeNote, "GPU 去畸變 55 張 · CPU 去畸變 0 張 · 沿用已完成影像 55 張");
  assert.equal(analysisRunDisplay({ image_probe_backends: { workers: 16 } }).probeNote, "自動並行 16 執行緒");
  assert.equal(analysisRunDisplay({
    image_probe_backends: { workers: 32, worker_limit: 128, tuning: 1 },
  }).probeNote, "自動並行 32 執行緒（試速中，上限 128）");
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

test("validation displays stage counts and actual GPU, conversion and CPU fallback counts", () => {
  const progress = normalizeAnalysisProgress({
    analysis_id: "test", status: "validating", stage: "validating_images",
    current_frame: 32, total_frames: 100, progress: .144,
    image_probe_backends: { gpu: 30, cpu: 2, converted: 32 },
  });
  const display = analysisRunDisplay(progress);
  assert.equal(display.progressTitle, "驗證進度");
  assert.equal(display.progressNote, "32 / 100 筆");
  assert.equal(display.stage, "轉檔並檢查影像");
  assert.equal(display.progressPercent, 14);
  assert.equal(display.probeNote, "轉檔 32 張 · GPU 30 張 · CPU 回退 2 張");
  assert.equal(analysisRunDisplay({ stage: "verifying_input_files", current_frame: 32, total_frames: 100 }).progressNote, "32 / 100 張");
  assert.equal(analysisRunDisplay({ stage: "checking_reconstruction_environment", current_frame: 0, total_frames: 1 }).progressNote, "0 / 1 項");
  assert.equal(analysisRunDisplay({ stage: "validation_completed", progress: 1 }).progressPercent, 100);
  assert.equal(analysisRunDisplay({}).progressNote, "準備中…");
});

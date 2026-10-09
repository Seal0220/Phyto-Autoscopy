import assert from "node:assert/strict";
import test from "node:test";
import { tipCorrectionPayload } from "../src/features/AnalysisRun/lib/analysisRoundTipUtils.js";
import { landmarkInModelSpace } from "../src/features/AnalysisRun/lib/analysisModelCoordinateUtils.js";
import { normalizeAnalysisProgress } from "../src/features/AnalysisRun/lib/analysisRunUtils.js";

const views = [
  { view_id: "top", camera_id: "top", snapshot_id: "same" },
  { view_id: "side", camera_id: "side", snapshot_id: "same" },
];
const points = { top: { x_px: 100, y_px: 200 }, side: { x_px: 80, y_px: 180 } };

test("inline tip marking sends only original clicks from the chosen simultaneous views", () => {
  assert.deepEqual(tipCorrectionPayload("round.94", views, { ...points, other: { x_px: 0, y_px: 0 } }), {
    round_key: "round.94", reason: "每輪影像人工尖端標記", invalid: false,
    observations: [{ view_id: "top", ...points.top }, { view_id: "side", ...points.side }],
  });
  const updated = tipCorrectionPayload("round.94", views, { ...points, top: { x_px: 120, y_px: 240 } });
  assert.equal(updated.observations[0].x_px, 120);
});

test("one camera, different snapshots, and nonfinite coordinates cannot be submitted", () => {
  assert.throws(() => tipCorrectionPayload("round.94", views, { top: points.top }), /俯視與側視/);
  assert.throws(() => tipCorrectionPayload("round.94", views.map((v) => ({ ...v, camera_id: "top" })), points), /俯視與側視/);
  assert.throws(() => tipCorrectionPayload("round.94", [views[0], { ...views[1], snapshot_id: "later" }], points), /同一組/);
  assert.throws(() => tipCorrectionPayload("round.94", views, { ...points, top: { x_px: NaN, y_px: 20 } }), /座標無效/);
});

test("world-space manual tips are transformed for the unchanged reference model", () => {
  const tip = { x_mm: 6, y_mm: 22, z_mm: 36, valid: true };
  const reference = { model_quality: { immutable_reference: true }, model_to_world: {
    scale: 2, rotation: [[0, -1, 0], [1, 0, 0], [0, 0, 1]], translation: [10, 20, 30],
  } };
  assert.deepEqual(landmarkInModelSpace(tip, reference), { x_mm: 1, y_mm: 2, z_mm: 3, valid: true });
  assert.equal(landmarkInModelSpace(tip, {}), tip);
  assert.equal(landmarkInModelSpace(tip, { model_quality: { immutable_reference: true } }), null);
  assert.deepEqual(tip, { x_mm: 6, y_mm: 22, z_mm: 36, valid: true });
});

test("live result revisions reach the run hook through progress normalization", () => {
  assert.equal(normalizeAnalysisProgress({ results_revision: "manual-change" }).results_revision, "manual-change");
});

test("rotating-arm clicks never replace the fixed stereo pair", () => {
  const all = [...views, { view_id: "rotating", camera_id: "rotating", snapshot_id: "same" }];
  const payload = tipCorrectionPayload("round.94", all, { ...points, rotating: { x_px: 50, y_px: 50 } });
  assert.deepEqual(payload.observations.map((point) => point.view_id), ["top", "side"]);
  assert.throws(() => tipCorrectionPayload("round.94", all, { top: points.top, rotating: points.side }), /俯視與側視/);
});

test("model picks submit a signed anchor instead of client coordinates or stale image clicks", () => {
  const signature = "a".repeat(64);
  assert.deepEqual(tipCorrectionPayload("round.94", views, points, { pointId: 12, signature }), {
    round_key: "round.94", model_point_id: 12, model_signature: signature, reason: "每輪模型人工尖端標記", invalid: false,
  });
  assert.throws(() => tipCorrectionPayload("round.94", views, {}, { pointId: -1, signature }), /無效/);
  assert.throws(() => tipCorrectionPayload("round.94", views, {}, { pointId: 12, signature: "old" }), /無效/);
});

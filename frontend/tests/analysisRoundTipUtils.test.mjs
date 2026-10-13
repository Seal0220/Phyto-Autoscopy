import assert from "node:assert/strict";
import test from "node:test";
import { tipCorrectionPayload } from "../src/features/AnalysisRun/lib/analysisRoundTipUtils.js";
import { landmarkInModelSpace, savedModelTipLandmark, trackedModelTipLandmark } from "../src/features/AnalysisRun/lib/analysisModelCoordinateUtils.js";

test("new tracking evidence replaces a persisted result from the older tracker", () => {
  const base = { status: "tracked", coordinate_space: "model", model_signature: "model", source: "temporal_tracking" };
  const reference = { signature: "model", model_tip: { ...base, relative_xyz: [4, 5, 6], quality: { version: 2 } } };
  const previous = { tracking: { model_tip: { ...base, relative_xyz: [1, 2, 3], quality: { version: 1 } } } };
  assert.deepEqual(trackedModelTipLandmark(reference, previous), {
    x_mm: 4, y_mm: 5, z_mm: 6, coordinate_space: "model", source: "temporal_tracking", valid: false,
  });
  assert.equal(trackedModelTipLandmark({ ...reference, model_tip: { status: "unavailable", tracking_version: 2 } }, previous), null);
});
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

test("tracked model annotations stay in their signed model frame without entering metric trajectories", () => {
  const tip = { status: "tracked", source: "temporal_tracking", coordinate_space: "model", model_signature: "new-model", relative_xyz: [2, 3, 7] };
  const reference = { signature: "new-model", model_tip: tip, model_quality: { immutable_reference: true } };
  const landmark = trackedModelTipLandmark(reference);
  assert.equal(landmark.valid, false);
  assert.equal(landmark.source, "temporal_tracking");
  assert.equal(landmarkInModelSpace(landmark, reference), landmark);
  assert.equal(trackedModelTipLandmark({ ...reference, signature: "other-model" }), null);
  assert.equal(trackedModelTipLandmark({ ...reference, model_tip: { ...tip, status: "unavailable" } }), null);
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

test("model and fixed-image picks are saved together without client model coordinates", () => {
  const signature = "a".repeat(64);
  assert.deepEqual(tipCorrectionPayload("round.94", views, points, { pointId: 12, signature }), {
    round_key: "round.94", model_point_id: 12, model_signature: signature, reason: "每輪影像人工尖端標記", invalid: false,
    observations: [{ view_id: "top", ...points.top }, { view_id: "side", ...points.side }],
  });
  assert.throws(() => tipCorrectionPayload("round.94", views, {}, { pointId: -1, signature }), /無效/);
  assert.throws(() => tipCorrectionPayload("round.94", views, {}, { pointId: 12, signature: "old" }), /無效/);
});

test("initialization requires the model pick and both simultaneous fixed images", () => {
  const options = { initializing: true, requireModel: true };
  const model = { pointId: 0, signature: "c".repeat(64) };
  assert.throws(() => tipCorrectionPayload("r", views, points, null, options), /第一輪模型/);
  assert.throws(() => tipCorrectionPayload("r", views, {}, model, options), /俯視與側視/);
  assert.equal(tipCorrectionPayload("r", views, points, model, options).model_point_id, 0);
});

test("saved auxiliary model tips remain visible without claiming metric confirmation", () => {
  const reference = { signature: "a".repeat(64), model_quality: { immutable_reference: true } };
  const correction = { model_signature: reference.signature, model_point_relative_xyz: [1, 2, 3] };
  const tip = savedModelTipLandmark(correction, reference);
  assert.deepEqual(tip, { x_mm: 1, y_mm: 2, z_mm: 3, valid: false, coordinate_space: "model" });
  assert.equal(landmarkInModelSpace(tip, reference), tip);
  assert.equal(savedModelTipLandmark({ ...correction, model_signature: "changed" }, reference), null);
  assert.equal(savedModelTipLandmark({ ...correction, invalid: true }, reference), null);
});

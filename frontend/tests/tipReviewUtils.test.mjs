import assert from "node:assert/strict";
import test from "node:test";

import {
  correctionPayload,
  epipolarSegment,
  initialCorrectionDraft,
  normalizeFrameDetail,
  normalizePoint,
  pointInsideImage,
} from "../src/features/TipReview/lib/tipReviewUtils.js";

test("tip review normalizes backend points without changing automatic data", () => {
  const frame = normalizeFrameDetail({
    pair: { frame_id: 4 },
    top_detection: {
      automatic_detection: {
        selected_point: { x_px: 12.5, y_px: 18.25 },
        candidate_points: [{ x_px: 12.5, y_px: 18.25 }],
        contour: [[0, 1], [2, 3]],
        detection_type: "Automatic",
        valid: true,
      },
      resolved_detection: {
        selected_point: { x_px: 14, y_px: 20 },
        detection_type: "Manual",
        valid: true,
      },
    },
  });

  assert.deepEqual(frame.topDetection.automatic.selectedPoint, {
    x: 12.5,
    y: 18.25,
  });
  assert.deepEqual(frame.topDetection.resolved.selectedPoint, {
    x: 14,
    y: 20,
  });
  assert.deepEqual(normalizePoint({ x_px: 0, y_px: 0 }), { x: 0, y: 0 });
});

test("manual draft prefers latest correction and produces explicit payload", () => {
  const stored = {
    automatic: { selectedPoint: { x: 2, y: 3 } },
    resolved: { selectedPoint: { x: 4, y: 5 } },
  };
  const corrections = [
    {
      camera_id: "top",
      created_at: "2026-01-01T00:00:00Z",
      correctedPoint: { x: 8, y: 9 },
      invalid: false,
      reason: "尖端重疊",
    },
  ];
  const draft = initialCorrectionDraft(stored, corrections, "top");
  const payload = correctionPayload(7, "top", draft);

  assert.deepEqual(draft.point, { x: 8, y: 9 });
  assert.equal(payload.corrected_x_px, 8);
  assert.equal(payload.reason, "尖端重疊");
  assert.deepEqual(correctionPayload(7, "side", {
    point: null,
    invalid: true,
    reason: "遮擋",
  }), {
    frame_id: 7,
    camera_id: "side",
    corrected_x_px: null,
    corrected_y_px: null,
    reason: "遮擋",
    invalid: true,
  });
  assert.throws(
    () => correctionPayload(7, "top", { point: null, invalid: false }),
    /指定尖端位置/,
  );
});

test("epipolar line is clipped to natural image coordinates", () => {
  assert.deepEqual(epipolarSegment([0, 1, -50], 100, 80), [
    { x: 0, y: 50 },
    { x: 100, y: 50 },
  ]);
  assert.equal(pointInsideImage({ x: 99.999, y: 79.999 }, 100, 80), true);
  assert.equal(pointInsideImage({ x: 100, y: 80 }, 100, 80), false);
  assert.equal(pointInsideImage({ x: -0.01, y: 2 }, 100, 80), false);
});

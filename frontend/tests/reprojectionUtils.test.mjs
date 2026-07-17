import assert from "node:assert/strict";
import test from "node:test";

import {
  isHighReprojectionError,
  normalizeReprojectionErrors,
  reprojectionChartPoints,
  reprojectionHistogram,
  reprojectionStatistics,
} from "../src/features/ReprojectionErrors/lib/reprojectionUtils.js";

const errors = normalizeReprojectionErrors([
  {
    frame_id: 1,
    top_error_px: 2,
    side_error_px: 4,
    overall_error_px: 3,
    high_error: false,
  },
  {
    frame_id: 2,
    top_error_px: 11,
    side_error_px: 13,
    overall_error_px: 12,
    high_error: true,
  },
]);

test("reprojection statistics include mean, population std, and high ratio", () => {
  const statistics = reprojectionStatistics(errors);

  assert.equal(statistics.topMean, 6.5);
  assert.equal(statistics.sideMean, 8.5);
  assert.equal(statistics.overallMean, 7.5);
  assert.ok(Math.abs(statistics.standardDeviation - 4.6097722286464435) < 1e-12);
  assert.equal(statistics.maximum, 13);
  assert.equal(statistics.highCount, 1);
  assert.equal(statistics.highRatio, 0.5);
});

test("high-error classification uses either camera and a strict 10 px threshold", () => {
  assert.equal(isHighReprojectionError({ top: 12, side: 4, overall: 8 }), true);
  assert.equal(isHighReprojectionError({ top: 10, side: 10, overall: 10 }), false);
});

test("reprojection chart and histogram preserve every sample", () => {
  const points = reprojectionChartPoints(errors, "overall");
  const histogram = reprojectionHistogram(errors, 4);

  assert.equal(points.length, 2);
  assert.ok(points[1].plotX > points[0].plotX);
  assert.equal(
    histogram.reduce((sum, bin) => sum + bin.count, 0),
    errors.length,
  );
});

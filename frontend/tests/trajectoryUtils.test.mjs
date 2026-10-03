import assert from "node:assert/strict";
import test from "node:test";

import {
  buildFormalTrajectoryPlot,
  formalTrajectoryModeColors,
} from "../src/features/TrajectoryViewer/lib/trajectoryUtils.js";

test("每個擷取模式取得穩定且不同的軌跡顏色", () => {
  const colors = formalTrajectoryModeColors([
    { mode_id: "AngleInterval.01" },
    { mode_id: "AngleInterval.01" },
    { mode_id: "SpecificAngles.01" },
  ]);

  assert.equal(Object.keys(colors).length, 2);
  assert.notEqual(
    colors["AngleInterval.01"],
    colors["SpecificAngles.01"],
  );
});

test("三維圖表保留世界座標與缺失輪次，不跨模式連線", () => {
  const { traces, validCount } = buildFormalTrajectoryPlot([
    {
      mode_id: "AngleInterval.01", round_id: "round.01",
      point_index: 0, valid: true,
      x_mm: 1, y_mm: 2, z_mm: 3, confidence: 0.9,
    },
    {
      mode_id: "AngleInterval.01", round_id: "round.02",
      point_index: 1, valid: false,
      x_mm: null, y_mm: null, z_mm: null,
    },
    {
      mode_id: "AngleInterval.01", round_id: "round.03",
      point_index: 2, valid: true,
      x_mm: 4, y_mm: 5, z_mm: 6, confidence: 0.8,
      manually_corrected: true,
    },
    {
      mode_id: "SpecificAngles.01", round_id: "round.01",
      point_index: 0, valid: true,
      x_mm: 7, y_mm: 8, z_mm: 9, confidence: 0.7,
    },
  ]);

  assert.equal(validCount, 3);
  assert.deepEqual(traces[0].x, [1, null, 4]);
  assert.deepEqual(traces[0].y, [2, null, 5]);
  assert.deepEqual(traces[0].z, [3, null, 6]);
  assert.equal(traces[0].connectgaps, false);
  assert.equal(traces[0].marker.color[2], "#ffffff");
  assert.equal(traces[0].marker.symbol[0], "circle-open");
  assert.equal(traces[0].marker.symbol[2], "circle");
  assert.deepEqual(traces[1].x, [7]);
  assert.equal(traces.at(-1).name, "世界原點");
});

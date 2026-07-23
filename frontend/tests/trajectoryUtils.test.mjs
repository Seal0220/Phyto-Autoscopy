import assert from "node:assert/strict";
import test from "node:test";

import {
  formalTrajectoryModeColors,
  projectWorldTrajectory,
  trajectoryPolyline,
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

test("三維尖端標記可投影為有限的畫布座標", () => {
  const projected = projectWorldTrajectory(
    [{
      mode_id: "AngleInterval.01",
      point_index: 0,
      x: 1,
      y: 2,
      z: 3,
    }],
    [{
      id: "origin",
      point: [0, 0, 0],
    }],
  );

  assert.equal(projected.points.length, 1);
  assert.equal(projected.markers.length, 1);
  assert.equal(Number.isFinite(projected.points[0].plotX), true);
  assert.equal(Number.isFinite(projected.points[0].plotY), true);
  assert.equal(
    trajectoryPolyline(projected.points),
    `${projected.points[0].plotX},${projected.points[0].plotY}`,
  );
});

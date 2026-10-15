import assert from "node:assert/strict";
import test from "node:test";
import { formatElapsedPrecise } from "../src/lib/formatUtils.js";
import { trajectoryMetricSeries, trajectoryMetricTimeBounds, trajectoryMetricTicks } from "../src/features/TrajectoryViewer/lib/trajectoryMetricUtils.js";
import { TRAJECTORY_METRICS } from "../src/features/TrajectoryViewer/trajectoryViewerConfig.js";

test("完整經過時間包含日、時、分、秒、毫秒並在各單位正確進位", () => {
  for (const [value, expected] of [
    [0, "0日 00時 00分 00秒 000毫秒"],
    [0.005, "0日 00時 00分 00秒 005毫秒"],
    [93784.005, "1日 02時 03分 04秒 005毫秒"],
    [59.9996, "0日 00時 01分 00秒 000毫秒"],
    [3599.9996, "0日 01時 00分 00秒 000毫秒"],
    [86399.9996, "1日 00時 00分 00秒 000毫秒"],
  ]) assert.equal(formatElapsedPrecise(value), expected);
  for (const value of [null, undefined, "", NaN, Infinity, 1e308]) assert.equal(formatElapsedPrecise(value), "尚無資料");
});

const point = (index, extra = {}) => ({ mode_id: "mode-1", round_id: `round.${index}`, point_index: index,
  elapsed_seconds: index * 60.005, z_mm: 100 + index, confidence: .85, valid: true, ...extra });

test("時間軸保留毫秒精度、缺失處中斷，各模式仍各自繪圖", () => {
  const source = [point(0), point(1, { valid: false }), point(2), point(3), point(1, { mode_id: "mode-2" })];
  const original = structuredClone(source);
  const { series, hasTime } = trajectoryMetricSeries(source, TRAJECTORY_METRICS[0]);
  assert.equal(hasTime, true);
  assert.deepEqual(series.map(segment => segment.points.map(item => item.point_index)), [[0], [2, 3], [1]]);
  assert.equal(series[1].points[0].chartX, 120.01);
  assert.deepEqual(source, original);
  const { series: confidence } = trajectoryMetricSeries([point(0)], TRAJECTORY_METRICS[3]);
  assert.equal(confidence[0].points[0].chartY, 85);
});

test("缺少時間的舊資料使用一致輪次順序，不把輪次混進秒座標", () => {
  const { series, hasTime } = trajectoryMetricSeries([point(1), point(2, { elapsed_seconds: null })], TRAJECTORY_METRICS[0]);
  assert.equal(hasTime, false);
  assert.deepEqual(series[0].points.map(item => item.chartX), [1, 2]);
});

test("經過時間軸從零開始留白，單一零秒資料仍有有限範圍", () => {
  const bounds = trajectoryMetricTimeBounds([0, 100], true);
  assert.equal(bounds.minimum, 0);
  assert.equal(bounds.maximum, 108);
  assert.equal(bounds.span, 108);
  const single = trajectoryMetricTimeBounds([0], true);
  assert.equal(single.minimum, 0);
  assert.equal(single.span, 1);
  assert.deepEqual(trajectoryMetricTicks(160), [0, 1]);
  assert.deepEqual(trajectoryMetricTicks(1200), [0, .25, .5, .75, 1]);
});

import assert from "node:assert/strict";
import test from "node:test";
import { trajectoryFrames, trajectoryThroughFrame, trajectoryRoundModels, modelsForTrajectoryFrame } from "../src/features/TrajectoryViewer/lib/trajectoryPlaybackUtils.js";
import { buildFormalTrajectoryPlot, formalTrajectoryModeColors } from "../src/features/TrajectoryViewer/lib/trajectoryUtils.js";
import { trajectoryModelTransform, trajectoryModelWorldMatrix, trajectoryOverlayCamera } from "../src/features/TrajectoryViewer/lib/trajectoryModelOverlayUtils.js";
import { gaussianInWorldSpace, mergeTrajectoryGaussians } from "../src/features/TrajectoryViewer/lib/trajectoryGaussianBuffers.js";
import { SplatBuffer } from "@mkkellogg/gaussian-splats-3d";
import { Vector3, Vector4 } from "three";

const point = (index, extra = {}) => ({ mode_id: "mode-1", round_id: `round.${index}`, point_index: index,
  valid: true, x_mm: index, y_mm: 2, z_mm: 3, ...extra });

test("播放依時間前進，略過缺失座標並保留過去軌跡及中斷", () => {
  const trajectory = [point(99, { timestamp: "2026-10-13T01:00:00Z" }), point(100, { valid: false }),
    point(300, { timestamp: "2026-10-13T02:00:00Z" }), point(2, { mode_id: "mode-2", timestamp: "2026-10-13T00:00:00Z" })];
  const before = structuredClone(trajectory);
  const frames = trajectoryFrames(trajectory);
  assert.deepEqual(frames.map(frame => frame.point.round_id), ["round.2", "round.99", "round.300"]);
  const first = trajectoryThroughFrame(trajectory, frames, 0);
  assert.equal(buildFormalTrajectoryPlot(first).validCount, 1);
  const second = trajectoryThroughFrame(trajectory, frames, 1);
  assert.equal(buildFormalTrajectoryPlot(second).validCount, 2);
  assert.ok(second.includes(trajectory[1]));
  const all = trajectoryThroughFrame(trajectory, frames, 2);
  assert.deepEqual(buildFormalTrajectoryPlot(all).traces[0].x, [99, null, 300]);
  assert.equal(trajectoryThroughFrame(trajectory, frames, null), trajectory);
  assert.deepEqual(trajectory, before);
  assert.deepEqual(trajectoryFrames(structuredClone(trajectory)).map(frame => frame.key), frames.map(frame => frame.key));
});

test("線與點獨立關閉，模式顏色穩定，隱藏不移除有效測量", () => {
  const trajectory = [point(1), point(1, { mode_id: "mode-2" })];
  const modeColors = formalTrajectoryModeColors(trajectory);
  for (const [showLines, showPoints, mode] of [[true, true, "lines+markers"], [true, false, "lines"], [false, true, "markers"], [false, false, "markers"]]) {
    const plot = buildFormalTrajectoryPlot([trajectory[1]], { showLines, showPoints, modeColors });
    assert.equal(plot.validCount, 1);
    assert.equal(plot.traces[0].mode, mode);
    assert.equal(plot.traces[0].visible, showLines || showPoints);
    assert.equal(plot.traces[0].line.color, modeColors["mode-2"]);
    assert.equal(plot.traces.at(-1).visible, showPoints);
  }
});

test("播放只選取當輪當模式完成的模型，總覽包含所有完成輪次", () => {
  const rounds = [1, 2, 3].map(index => ({ round_key: `key:${index}`, mode_id: "mode-1", round_id: `round.${index}` }));
  const models = trajectoryRoundModels(rounds.map((round, index) => ({ round_key: round.round_key,
    status: index === 2 ? "training" : "completed", model_path: "model.ply" })), rounds);
  assert.equal(modelsForTrajectoryFrame(models, null).length, 2);
  assert.equal(modelsForTrajectoryFrame(models, trajectoryFrames([point(1)])[0])[0].round_key, "key:1");
  assert.deepEqual(modelsForTrajectoryFrame(models, trajectoryFrames([point(1, { mode_id: "mode-2" })])[0]), []);
});

test("沒有定位的相對模型、反射、變形與非有限校正不會當成毫米模型", () => {
  const identity = { scale: 1, rotation: [[1, 0, 0], [0, 1, 0], [0, 0, 1]], translation: [0, 0, 0] };
  assert.equal(trajectoryModelTransform({ model_quality: { coordinate_unit: "relative" } }), null);
  assert.equal(trajectoryModelTransform({}), null);
  assert.equal(trajectoryModelTransform({ model_quality: { immutable_reference: true, coordinate_unit: "millimetre" } }), null);
  assert.deepEqual(trajectoryModelTransform({ model_quality: { coordinate_unit: "millimetre" } }), identity);
  for (const transform of [{ ...identity, scale: 0 }, { ...identity, translation: [0, NaN, 0] },
    { ...identity, rotation: [[-1, 0, 0], [0, 1, 0], [0, 0, 1]] }, { ...identity, rotation: [[2, 0, 0], [0, 1, 0], [0, 0, 1]] }]) {
    assert.equal(trajectoryModelTransform({ model_to_world: transform }), null);
  }
  assert.deepEqual(trajectoryModelWorldMatrix({ ...identity, scale: 2, translation: [3, 4, 5] }),
    [2, 0, 0, 0, 0, 2, 0, 0, 0, 0, 2, 0, 3, 4, 5, 1]);
});

test("疊加採用實際 Plotly 縮放與投影矩陣，拒絕未初始化的場景", () => {
  const matrix = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 2, 3, 4, 1];
  const scene = { dataScale: [2, 3, 4], glplot: { canvas: {}, cameraParams: { view: matrix, projection: matrix, model: matrix } } };
  const snapshot = trajectoryOverlayCamera({ _fullLayout: { scene: { _scene: scene } } });
  assert.deepEqual(snapshot.world, [2, 0, 0, 0, 0, 3, 0, 0, 0, 0, 4, 0, 2, 3, 4, 1]);
  assert.deepEqual(snapshot.view, matrix);
  assert.equal(trajectoryOverlayCamera({}), null);
  scene.glplot.cameraParams.view[0] = Infinity;
  assert.equal(trajectoryOverlayCamera({ _fullLayout: { scene: { _scene: scene } } }), null);
});

test("疊加副本保留 Gaussian 形狀、透明度及位置，超過 32 輪仍完整合併", async () => {
  const { splatBuffer: source, splatBufferDataOffsetBytes: offset } = SplatBuffer.preallocateUncompressed(1, 2);
  const floats = new Float32Array(source.bufferData, offset);
  floats.set([1, 2, 3, 1, 2, 3, 1, 0, 0, 0]);
  new Uint8Array(source.bufferData, offset + 40, 4).set([100, 160, 200, 120]);
  floats[11] = 0.3; floats[12] = 0.4; floats[13] = 0.5;
  const original = source.bufferData.slice(0);
  const transform = { scale: 2, rotation: [[0, -1, 0], [1, 0, 0], [0, 0, 1]], translation: [10, 20, 30] };
  const world = await gaussianInWorldSpace(source, transform, new AbortController().signal);
  const center = new Vector3(), color = new Vector4(), covariance = new Float32Array(6);
  world.getSplatCenter(0, center);
  assert.deepEqual(center.toArray(), [6, 22, 36]);
  world.getSplatColor(0, color);
  assert.deepEqual(color.toArray(), [100, 160, 200, 120]);
  world.fillSplatCovarianceArray(covariance, undefined, undefined, undefined, undefined, 0);
  for (const [index, expected] of [[0, 16], [3, 4], [5, 36]]) assert.ok(Math.abs(covariance[index] - expected) < 1e-5);
  const sh = new Float32Array(24); world.fillSphericalHarmonicsArray(sh, 2, undefined, undefined, undefined, undefined, 0);
  assert.ok(Math.abs(sh.reduce((sum, value) => sum + value ** 2, 0) - 0.5) < 1e-6);
  assert.deepEqual(source.bufferData, original);
  const merged = mergeTrajectoryGaussians(Array(40).fill(world));
  assert.equal(merged.getSplatCount(), 40);
  merged.getSplatCenter(39, center);
  assert.deepEqual(center.toArray(), [6, 22, 36]);
  const cancelled = new AbortController(); cancelled.abort();
  await assert.rejects(gaussianInWorldSpace(source, transform, cancelled.signal), { name: "AbortError" });
});

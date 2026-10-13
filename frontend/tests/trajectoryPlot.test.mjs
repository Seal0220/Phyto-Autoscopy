import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import vm from "node:vm";
import { currentTrajectoryCamera, defaultTrajectoryCamera, formalTrajectoryPlotLayout } from "../src/features/TrajectoryViewer/lib/trajectoryPlotUtils.js";
import { TRAJECTORY_PLOT_CONFIG } from "../src/features/TrajectoryViewer/trajectoryViewerConfig.js";

const require = createRequire(import.meta.url);
const swc = require("next/dist/build/swc");
await swc.loadBindings();
const source = new URL("../src/features/TrajectoryViewer/hooks/useFormalTrajectoryPlot.js", import.meta.url);
const { code } = swc.transformSync(readFileSync(source, "utf8"), {
  filename: source.pathname,
  jsc: { parser: { syntax: "ecmascript" } },
  module: { type: "commonjs" },
});

function plotHarness() {
  const slots = [], pending = [], calls = [], listeners = new Map();
  let cursor = 0, rejectDraw = false, liveLayout, renderedCamera;
  const element = {
    isConnected: true, parentElement: {},
    on(event, callback) { listeners.set(event, callback); },
    removeListener(event) { listeners.delete(event); },
  };
  const plotly = {
    async react(target, traces, layout) {
      calls.push({ type: "draw", layout, traces });
      if (rejectDraw) throw new Error("WebGL failure");
      liveLayout = layout;
      renderedCamera = layout.scene.camera;
      element._fullLayout = { scene: { _scene: { getCamera: () => renderedCamera } } };
    },
    purge() { calls.push({ type: "purge" }); },
    async relayout(target, event) {
      calls.push({ type: "reset", event });
      liveLayout.scene.camera = event["scene.camera"];
      renderedCamera = event["scene.camera"];
      listeners.get("plotly_relayout")?.(event);
    },
  };
  const react = {
    useRef(value) {
      const index = cursor++;
      return slots[index] ||= { current: value };
    },
    useState(value) {
      const index = cursor++;
      slots[index] ||= { value };
      return [slots[index].value, next => {
        slots[index].value = typeof next === "function" ? next(slots[index].value) : next;
      }];
    },
    useEffect(callback, dependencies) {
      const index = cursor++;
      const previous = slots[index];
      if (!previous || dependencies.some((value, position) => !Object.is(value, previous.dependencies[position]))) {
        pending.push({ index, callback, cleanup: previous?.cleanup, dependencies });
      }
    },
  };
  const compiled = { exports: {} };
  const dependencies = {
    react,
    "../trajectoryViewerConfig": { TRAJECTORY_PLOT_CONFIG },
    "../lib/trajectoryPlotUtils": { currentTrajectoryCamera, defaultTrajectoryCamera, formalTrajectoryPlotLayout },
    "plotly.js-gl3d-dist-min": plotly,
  };
  const context = vm.createContext({
    require: name => dependencies[name], module: compiled, exports: compiled.exports, structuredClone,
    ResizeObserver: class { observe() {} disconnect() {} }, cancelAnimationFrame() {},
  });
  vm.runInContext(code, context);
  return {
    calls,
    render(props) {
      cursor = 0;
      const state = compiled.exports.default(props);
      state.plotElementRef.current = element;
      for (const effect of pending) effect.cleanup?.();
      for (const effect of pending.splice(0)) {
        slots[effect.index] = { dependencies: effect.dependencies, cleanup: effect.callback() };
      }
      return state;
    },
    camera(camera) { renderedCamera = camera; },
    fail(value) { rejectDraw = value; },
    unmount() { for (const slot of slots) slot.cleanup?.(); },
  };
}

const drain = () => new Promise(resolve => setImmediate(resolve));
const props = {
  analysisId: "test", hasPoints: true,
  traces: [{ type: "scatter3d", x: [1], y: [2], z: [3] }],
  ranges: { x: [-10, 10], y: [-10, 10], z: [-10, 10] },
};

test("camera snapshots tolerate an unavailable or malformed renderer", () => {
  const fallback = defaultTrajectoryCamera();
  assert.equal(currentTrajectoryCamera(null, fallback), fallback);
  const renderer = { _fullLayout: { scene: { _scene: { getCamera: () => ({ eye: { x: NaN } }) } } } };
  assert.equal(currentTrajectoryCamera(renderer, fallback), fallback);
});

test("polling and new points retain the camera and never purge the active plot", async () => {
  const harness = plotHarness();
  harness.render(props);
  await drain();
  const camera = { eye: { x: 2, y: -1, z: .7 }, up: { x: 0, y: 0, z: 1 }, center: { x: .1, y: .2, z: -.1 } };
  harness.camera(camera);
  const updated = { ...props, traces: [{ ...props.traces[0], x: [1, 2], y: [2, 3], z: [3, 4] }] };
  let state = harness.render(updated);
  await drain();
  assert.equal(harness.calls.filter(call => call.type === "purge").length, 0);
  assert.deepEqual(JSON.parse(JSON.stringify(harness.calls.at(-1).layout.scene.camera)), camera);
  assert.equal(harness.calls.at(-1).layout.scene.uirevision, harness.calls[0].layout.scene.uirevision);
  state = harness.render(updated);
  assert.equal(state.loading, false);
  state.resetCamera();
  await drain();
  assert.deepEqual(JSON.parse(JSON.stringify(harness.calls.at(-1).event["scene.camera"])), defaultTrajectoryCamera());
  harness.unmount();
  await drain();
  assert.equal(harness.calls.at(-1).type, "purge");
});

test("switching analyses purges the previous plot before drawing the new one", async () => {
  const harness = plotHarness();
  harness.render(props);
  await drain();
  harness.render({ ...props, analysisId: "another" });
  await drain();
  assert.deepEqual(harness.calls.map(call => call.type), ["draw", "purge", "draw"]);
  assert.notEqual(harness.calls[0].layout.uirevision, harness.calls.at(-1).layout.uirevision);
  harness.unmount();
  await drain();
});

test("a failed draw releases loading and can retry without poisoning the render queue", async () => {
  const harness = plotHarness();
  harness.fail(true);
  harness.render(props);
  await drain();
  const failed = harness.render(props);
  assert.equal(failed.loading, false);
  assert.ok(failed.loadError.includes("三維軌跡"));
  harness.fail(false);
  failed.retry();
  harness.render(props);
  await drain();
  const recovered = harness.render(props);
  assert.equal(recovered.loadError, "");
  assert.equal(recovered.loading, false);
  assert.deepEqual(harness.calls.map(call => call.type), ["draw", "purge", "draw"]);
  harness.unmount();
  await drain();
});

import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import vm from "node:vm";
import * as utils from "../src/features/AnalysisRun/lib/analysisStereoReviewUtils.js";

const require = createRequire(import.meta.url);
const swc = require("next/dist/build/swc");
await swc.loadBindings();
const filename = new URL("../src/features/AnalysisRun/components/AnalysisRunStereoReviewImage.js", import.meta.url);
const { code } = swc.transformSync(readFileSync(filename, "utf8"), {
  filename: filename.pathname,
  jsc: { parser: { syntax: "ecmascript", jsx: true }, transform: { react: { runtime: "automatic" } } },
  module: { type: "commonjs" },
});

function fixture(disabled = false) {
  const module = { exports: {} };
  let stateIndex = 0;
  const react = {
    useRef: (current) => ({ current }),
    useState: (value) => [stateIndex++ === 0 ? true : value, () => {}],
  };
  function resolve(name) {
    if (name === "react") return react;
    if (name.includes("analysisStereoReviewUtils")) return utils;
    if (name.includes("analysisConfig")) return { ANALYSIS_CAMERA_LABELS: { top: "俯視角" } };
    if (name.includes("analysisImageUtils")) return { analysisViewImageUrl: () => "/image" };
    if (name.startsWith("@/components/")) return { __esModule: true, default: () => null };
    return require(name);
  }
  vm.runInThisContext(`(function(require,module,exports){${code}\n})`)(resolve, module, module.exports);
  const calls = { change: [], remove: [] };
  const pairs = [{ top: { x_px: 100, y_px: 200 } }, { top: { x_px: 400, y_px: 300 } }];
  const tree = module.exports.default({
    analysisId: "test", view: { camera_id: "top", image_width: 1280, image_height: 960, view_id: "t" },
    pairs, selected: 0, disabled,
    onPointChange: (...values) => calls.change.push(values),
    onPairRemove: (index) => calls.remove.push(index),
  });
  const overlay = tree.props.children[1].props.children.find((node) => node?.type === "svg");
  const captures = new Set();
  const target = {
    getBoundingClientRect: () => ({ left: 0, top: 0, width: 1000, height: 500 }),
    focus() {},
    setPointerCapture: (id) => captures.add(id),
    hasPointerCapture: (id) => captures.has(id),
    releasePointerCapture: (id) => captures.delete(id),
  };
  const event = (values = {}) => ({
    currentTarget: target, target: { closest: () => null }, button: 0, pointerId: 1, isPrimary: true,
    // Native (400, 300) projected into a 1000x500 letterboxed image.
    clientX: 500 - 240 * 500 / 960, clientY: 300 * 500 / 960,
    preventDefault() {}, ...values,
  });
  return { handlers: overlay.props, calls, event, captures, pairs };
}

test("dragging a nonselected image marker edits its own pair in native pixels", () => {
  const f = fixture();
  f.handlers.onPointerDown(f.event({ target: { closest: () => ({ dataset: { stereoPair: "1" } }) } }));
  assert.deepEqual(f.calls.change[0], ["top", f.pairs[1].top, 1]);
  assert.equal(f.captures.has(1), true);
  f.handlers.onPointerMove(f.event({ clientX: 500 - 230 * 500 / 960, clientY: 320 * 500 / 960 }));
  const [camera, point, index] = f.calls.change.at(-1);
  assert.equal(camera, "top");
  assert.equal(index, 1);
  assert.ok(Math.abs(point.x_px - 410) < 1e-8);
  assert.ok(Math.abs(point.y_px - 320) < 1e-8);
  f.handlers.onPointerUp(f.event());
  assert.equal(f.captures.has(1), false);
  const count = f.calls.change.length;
  f.handlers.onPointerMove(f.event());
  assert.equal(f.calls.change.length, count);
});

test("right-click removes the hit image group without placing a new point", () => {
  const f = fixture();
  f.handlers.onPointerDown(f.event({ button: 2 }));
  assert.equal(f.calls.change.length, 0);
  f.handlers.onContextMenu(f.event({ target: { closest: () => ({ dataset: { stereoPair: "1" } }) } }));
  assert.deepEqual(f.calls.remove, [1]);
  f.handlers.onContextMenu(f.event());
  assert.deepEqual(f.calls.remove, [1]);
});

test("cancelling an image drag restores its original coordinate and releases capture", () => {
  for (const cancel of ["pointer", "keyboard"]) {
    const f = fixture();
    f.handlers.onPointerDown(f.event({ target: { closest: () => ({ dataset: { stereoPair: "1" } }) } }));
    f.handlers.onPointerMove(f.event({ clientX: 500 }));
    if (cancel === "pointer") f.handlers.onPointerCancel(f.event());
    else f.handlers.onKeyDown(f.event({ key: "Escape" }));
    assert.deepEqual(f.calls.change.at(-1), ["top", f.pairs[1].top, 1]);
    assert.equal(f.captures.has(1), false);
  }
});

test("keyboard deletion ends an image drag so subsequent motion cannot edit another group", () => {
  const f = fixture();
  f.handlers.onPointerDown(f.event({ target: { closest: () => ({ dataset: { stereoPair: "1" } }) } }));
  f.handlers.onKeyDown(f.event({ key: "Delete" }));
  const count = f.calls.change.length;
  f.handlers.onPointerMove(f.event({ clientX: 500 }));
  assert.equal(f.calls.change.length, count);
  assert.equal(f.captures.has(1), false);
  assert.deepEqual(f.calls.remove, [1]);
});

test("disabled images block drag, right-click deletion and keyboard editing", () => {
  const f = fixture(true);
  f.handlers.onPointerDown(f.event());
  f.handlers.onContextMenu(f.event({ target: { closest: () => ({ dataset: { stereoPair: "1" } }) } }));
  f.handlers.onKeyDown(f.event({ key: "Delete" }));
  f.handlers.onKeyDown(f.event({ key: "ArrowRight" }));
  assert.deepEqual(f.calls, { change: [], remove: [] });
});

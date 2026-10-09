import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import vm from "node:vm";
import { tipCorrectionPayload } from "../src/features/AnalysisRun/lib/analysisRoundTipUtils.js";

const require = createRequire(import.meta.url);
const swc = require("next/dist/build/swc");
await swc.loadBindings();
class UnknownOutcome extends Error {}

function harness(saveRequest, onSaved = async () => true) {
  const state = [], refs = [], effects = [], pending = [];
  let index = 0;
  const react = {
    useState(initial) {
      const slot = index++;
      if (!(slot in state)) state[slot] = initial;
      return [state[slot], (value) => { state[slot] = typeof value === "function" ? value(state[slot]) : value; }];
    },
    useRef(initial) {
      const slot = index++;
      refs[slot] ||= { current: initial };
      return refs[slot];
    },
    useEffect(callback, deps) {
      const slot = index++;
      if (!effects[slot] || deps.some((value, i) => value !== effects[slot].deps[i])) {
        pending.push(() => {
          effects[slot]?.cleanup?.();
          effects[slot] = { deps, cleanup: callback() };
        });
      }
    },
  };
  const source = new URL("../src/features/AnalysisRun/hooks/useAnalysisRunTipCorrection.js", import.meta.url);
  const { code } = swc.transformSync(readFileSync(source, "utf8"), {
    filename: source.pathname, jsc: { parser: { syntax: "ecmascript" } }, module: { type: "commonjs" },
  });
  const compiled = { exports: {} };
  const dependencies = {
    react,
    "@/lib/httpUtils": { messageFromError: (error) => error.message },
    "@/features/TipReview/lib/formalTipReviewApiUtils": { saveFormalTipCorrection: saveRequest },
    "../lib/analysisRunApiUtils": { UnknownAnalysisMutationOutcomeError: UnknownOutcome },
    "../lib/analysisRoundTipUtils": { tipCorrectionPayload },
  };
  vm.runInThisContext(`(function(require,module,exports){${code}\n})`)((name) => dependencies[name], compiled, compiled.exports);
  let props = { analysisId: "analysis", roundKey: "round.94", onSaved, views: [
    { view_id: "top", camera_id: "top", snapshot_id: "same" },
    { view_id: "side", camera_id: "side", snapshot_id: "same" },
  ] };
  function render(update = {}) {
    props = { ...props, ...update };
    index = 0;
    const value = compiled.exports.default(props);
    pending.splice(0).forEach((effect) => effect());
    return value;
  }
  function marked() {
    render().updatePoint("top", { x_px: 10, y_px: 20 });
    render().updatePoint("side", { x_px: 15, y_px: 25 });
    return render();
  }
  return { render, marked, unmount: () => effects.forEach((effect) => effect?.cleanup?.()) };
}

test("original saved clicks can be moved without being reset by polling the same correction", () => {
  const app = harness(async () => ({}));
  const correction = { correction_id: "saved", observations: [{ view_id: "top", x_px: 10, y_px: 20 }] };
  app.render({ correction });
  app.render().updatePoint("top", { x_px: 30, y_px: 40 });
  assert.equal(app.render({ correction: { ...correction } }).points.top.x_px, 30);
  app.unmount();
});

test("automatically tracked image points remain editable and confirmation differs from metric calibration", async () => {
  const app = harness(async () => ({ tracking_seed_confirmed: true, pending_alignment: true }));
  const landmark = { tip_id: "tracked", image_observations: [
    { view_id: "top", x_px: 10, y_px: 20 }, { view_id: "side", x_px: 15, y_px: 25 },
  ] };
  app.render({ landmark });
  assert.equal(app.render().points.top.x_px, 10);
  app.render().updatePoint("top", { x_px: 12, y_px: 22 });
  assert.equal(app.render({ landmark: { ...landmark } }).points.top.x_px, 12);
  await app.render().save();
  assert.match(app.render().notice, /影像已確認/);
  assert.match(app.render().notice, /量測校正通過/);
  app.unmount();
});

test("duplicate saves are blocked and uncertain saves require a confirmed read before retry", async () => {
  let reject, calls = 0, readSucceeded = false;
  const app = harness(() => { calls++; return new Promise((_, failure) => { reject = failure; }); }, async () => readSucceeded);
  const hook = app.marked();
  const saved = hook.save();
  await hook.save();
  assert.equal(calls, 1);
  reject(new UnknownOutcome("結果不確定"));
  await saved;
  assert.equal(app.render().saving, false);
  assert.equal(app.render().unknown, true);
  await app.render().save();
  assert.equal(calls, 1);
  await app.render().refresh();
  assert.equal(app.render().unknown, true);
  readSucceeded = true;
  await app.render().refresh();
  assert.equal(app.render().unknown, false);
  app.unmount();
});

test("successful writes remain confirmed even if refreshing the screen fails", async () => {
  let calls = 0;
  const app = harness(async () => { calls++; return { pending_alignment: true }; }, async () => { throw new Error("read failed"); });
  await app.marked().save();
  assert.equal(calls, 1);
  assert.equal(app.render().unknown, false);
  assert.match(app.render().notice, /已儲存/);
  assert.match(app.render().error, /畫面更新失敗/);
  app.unmount();
});

test("a late completion cannot update another round or refresh after unmount", async () => {
  let resolve, signal, reloads = 0;
  const app = harness((_, __, requestSignal) => {
    signal = requestSignal;
    return new Promise((done) => { resolve = done; });
  }, async () => { reloads++; return true; });
  const saving = app.marked().save();
  app.render({ roundKey: "round.95" });
  assert.equal(signal.aborted, true);
  resolve({});
  await saving;
  assert.equal(reloads, 0);
  assert.equal(app.render().notice, "");
  app.unmount();
});

test("image and model edits alternate safely and a saved model anchor can be modified", async () => {
  const payloads = [];
  const app = harness(async (_, payload) => { payloads.push(payload); return {}; });
  const reference = { signature: "b".repeat(64) };
  app.render({ correction: { correction_id: "model", model_point_id: 2, model_signature: reference.signature } });
  assert.equal(app.render().modelSelection.pointId, 2);
  app.render().selectModelPoint(8, reference);
  await app.render().save();
  assert.equal(payloads[0].model_point_id, 8);
  assert.equal(payloads[0].observations, undefined);
  const images = app.marked();
  assert.equal(images.modelSelection, null);
  await images.save();
  assert.equal(payloads[1].model_point_id, undefined);
  assert.equal(payloads[1].observations.length, 2);
  app.render().selectModelPoint(12, reference);
  assert.deepEqual(app.render().points, {});
  app.render().selectModelPoint(null, reference);
  assert.equal(app.render().modelSelection, null);
  app.unmount();
});

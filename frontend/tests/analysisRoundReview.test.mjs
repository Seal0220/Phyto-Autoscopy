import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import vm from "node:vm";

const require = createRequire(import.meta.url);
const swc = require("next/dist/build/swc");
await swc.loadBindings();

function component(filename, overrides) {
  const source = new URL(`../src/features/AnalysisRun/${filename}`, import.meta.url);
  const { code } = swc.transformSync(readFileSync(source, "utf8"), {
    filename: source.pathname,
    jsc: { parser: { syntax: "ecmascript", jsx: true }, transform: { react: { runtime: "automatic" } } },
    module: { type: "commonjs" },
  });
  const compiledModule = { exports: {} };
  const resolve = (name) => {
    if (name in overrides) return overrides[name];
    if (name === "react/jsx-runtime") return require(name);
    return { __esModule: true, default: name.split("/").at(-1) };
  };
  vm.runInThisContext(`(function(require,module,exports){${code}\n})`)(resolve, compiledModule, compiledModule.exports);
  return compiledModule.exports.default;
}

function descendants(node) {
  if (!node || typeof node !== "object") return [];
  return [node, ...[node.props?.children].flat(Infinity).flatMap(descendants)];
}

test("round results retain the measured tip and open manual tip correction for that round", () => {
  const markingUpdates = [];
  let index = 0;
  const RoundRow = component("components/AnalysisRunRoundRow.js", {
    react: { useState: (value) => {
      const current = index++;
      return [current === 0 ? true : value, current === 2 ? (update) => markingUpdates.push(update(false)) : () => {}];
    } },
    "@/features/Analysis/analysisConfig": { ANALYSIS_MODEL_STATUS_META: {
      alignment_pending: { label: "待相機對齊", tone: "warning" },
    } },
    "@/lib/formatUtils": { formatNumberWithUnit: String },
    "../lib/analysisRunUtils": { analysisRoundStatus: () => ({ label: "完成", tone: "success" }) },
    "../hooks/useAnalysisRunRoundRetry": { __esModule: true, default: () => ({ saving: false, retry() {} }) },
  });
  const round = { round_key: "record:mode-1:round.94", status: "tip_completed" };
  const landmark = { valid: true, confidence: .9, x_mm: 2, y_mm: 3, z_mm: 4 };
  const tree = RoundRow({ analysisId: "analysis-test", round, model: {}, landmark, onReloadRun() {} });
  const nodes = descendants(tree);
  assert.equal(nodes.find((node) => node.type === "AnalysisRunModelPreview").props.landmark, landmark);
  const button = nodes.find((node) => node.props?.children === "修改尖端");
  assert.equal(button.props.disabled, false);
  button.props.onClick();
  assert.deepEqual(markingUpdates, [true]);
});

test("a pending round permits inline tip marking while another round trains", () => {
  let index = 0;
  const RoundRow = component("components/AnalysisRunRoundRow.js", {
    react: { useState: () => [index++ < 2, () => {}] },
    "next/navigation": { useRouter: () => ({ push() {} }) },
    "@/features/Analysis/analysisConfig": { ANALYSIS_MODEL_STATUS_META: {
      alignment_pending: { label: "待相機對齊", tone: "warning" },
    } },
    "@/lib/formatUtils": { formatNumberWithUnit: String },
    "../lib/analysisRunUtils": { analysisRoundStatus: () => ({ label: "待補正", tone: "warning" }) },
    "../hooks/useAnalysisRunRoundRetry": { __esModule: true, default: () => ({ saving: false, retry() {} }) },
  });
  const round = { round_key: "record:mode-1:round.01", status: "alignment_pending" };
  const tree = RoundRow({ analysisId: "analysis-test", round, busy: true, model: { status: "alignment_pending" }, onReloadRun() {} });
  const nodes = descendants(tree);
  assert.deepEqual(descendants(tree.props.title).map((node) => node.props?.children).filter((value) => typeof value === "string"), ["待補正"]);
  assert.equal(nodes.find((node) => node.type === "AnalysisRunStereoReview").props.roundKey, round.round_key);
  assert.equal(nodes.find((node) => node.props?.children === "標記尖端").props.disabled, false);
});

test("a completed model preview passes the tip coordinates to its 3D viewer", () => {
  const reference = { signature: "model", gaussian_path: "model.ply" };
  const Preview = component("components/AnalysisRunModelPreview.js", {
    "../hooks/useAnalysisRunModelPreview": { __esModule: true, default: () => ({ reference }) },
  });
  const landmark = { x_mm: 10, y_mm: 20, z_mm: 30, valid: false };
  const node = Preview({ analysisId: "analysis-test", model: { status: "completed", model_path: "model.ply" }, landmark });
  const viewer = node.type(node.props);
  assert.equal(viewer.type, "AnalysisRunModelReference");
  assert.equal(viewer.props.landmark, landmark);
  assert.equal(viewer.props.reference, reference);
});

test("inline editor offers only top and side images with one model below them", () => {
  const tip = { points: {}, updatePoint() {}, removePoint() {} };
  const Editor = component("components/AnalysisRunRoundTipEditor.js", {
    "../hooks/useAnalysisRunTipCorrection": { __esModule: true, default: () => tip },
  });
  const model = { status: "completed", model_path: "model.ply" };
  const tree = Editor({ analysisId: "a", roundKey: "r", model, views: [
    { view_id: "arm", camera_id: "rotating" }, { view_id: "side", camera_id: "side" }, { view_id: "top", camera_id: "top" },
  ] });
  const nodes = descendants(tree);
  assert.deepEqual(nodes.filter((node) => node.type === "FormalTipReviewRoundImage").map((node) => node.props.view.camera_id), ["top", "side"]);
  const modelNode = nodes.find((node) => node.type === "AnalysisRunRoundTipModel");
  assert.equal(modelNode.props.model, model);
  assert.ok(nodes.indexOf(modelNode) > nodes.findLastIndex((node) => node.type === "FormalTipReviewRoundImage"));
});

test("model tip selection, drag and removal share one signed point, while polling preserves selection", () => {
  const reference = { signature: "a".repeat(64) };
  const picked = [];
  const Model = component("components/AnalysisRunRoundTipModel.js", {
    "../hooks/useAnalysisRunModelPreview": { __esModule: true, default: () => ({ reference }) },
  });
  const tip = { modelSelection: { pointId: 0, signature: reference.signature }, selectModelPoint: (...args) => picked.push(args) };
  const viewer = Model({ analysisId: "a", model: {}, landmark: { valid: true }, tip });
  assert.equal(viewer.props.tipPicking, true);
  assert.equal(viewer.props.landmark, null);
  assert.deepEqual(viewer.props.pointIds, [0]);
  viewer.props.onPointChange(3);
  viewer.props.onPointMove(3, 8);
  viewer.props.onPointRemove(8);
  assert.deepEqual(picked, [[3, reference], [8, reference], [null, reference]]);
});

test("hovering a leaf correspondence highlights only its matching point in the other view", () => {
  const Markers = component("components/AnalysisRunImageFeatureMarkers.js", {});
  const features = [
    { feature_id: "leaf-1", error_px: .4, observations: [
      { view_id: "top", x_px: 60, y_px: 40 }, { view_id: "side", x_px: 100, y_px: 70 },
    ] },
    { feature_id: "leaf-2", error_px: .7, observations: [{ view_id: "side", x_px: 30, y_px: 20 }] },
  ];
  let activeFeature = null;
  const shared = { features, width: 200, height: 100, onActiveFeature: (value) => { activeFeature = value; } };
  const [top] = Markers({ ...shared, viewId: "top", activeFeature });
  top.props.onPointerEnter();
  const [matching, other] = Markers({ ...shared, viewId: "side", activeFeature });
  assert.match(matching.props.className, /border-white bg-cyan-300/);
  assert.doesNotMatch(other.props.className, /border-white bg-cyan-300/);
  assert.equal(matching.props.style.left, "50%");
  matching.props.onPointerLeave();
  assert.equal(activeFeature, null);
  top.props.onFocus();
  assert.equal(activeFeature, "leaf-1");
});

test("the first round opens the fixed image editor while waiting for manual initialization", () => {
  const RoundRow = component("components/AnalysisRunRoundRow.js", {
    react: { useState: (value) => [value, () => {}] },
    "@/features/Analysis/analysisConfig": { ANALYSIS_MODEL_STATUS_META: {} },
    "@/lib/formatUtils": { formatNumberWithUnit: String },
    "../lib/analysisRunUtils": { analysisRoundStatus: () => ({ label: "等待初始化", tone: "warning" }) },
    "../hooks/useAnalysisRunRoundRetry": { __esModule: true, default: () => ({ saving: false }) },
  });
  const tree = RoundRow({ analysisId: "a", round: { round_key: "r", status: "waiting_tip_seed" } });
  assert.equal(tree.props.open, true);
  assert.equal(descendants(tree).find((node) => node.type === "AnalysisRunRoundImages").props.marking, true);
});

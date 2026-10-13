import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import vm from "node:vm";
import { savedModelTipLandmark, trackedModelTipLandmark } from "../src/features/AnalysisRun/lib/analysisModelCoordinateUtils.js";
import * as tipResults from "../src/features/AnalysisRun/lib/analysisTipResultsUtils.js";

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
    if (name === "../lib/analysisTipResultsUtils") return tipResults;
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

function textContent(node) {
  if (typeof node === "string") return node;
  if (!node || typeof node !== "object") return "";
  return [node.props?.children].flat(Infinity).map(textContent).join("");
}

test("round results retain the measured tip and open manual tip correction for that round", () => {
  const markingUpdates = [];
  const RoundDetail = component("components/AnalysisRunRoundDetail.js", {
    react: { useState: (value) => {
      return [value, (update) => markingUpdates.push(typeof update === "function" ? update(false) : update)];
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
  const tree = RoundDetail({ analysisId: "analysis-test", round, model: {}, landmark, onReloadRun() {} });
  const nodes = descendants(tree);
  assert.equal(nodes.find((node) => node.type === "AnalysisRunModelPreview").props.landmark, landmark);
  const button = nodes.find((node) => node.type === "Button" && textContent(node) === "修改尖端");
  assert.equal(button.props.disabled, false);
  assert.ok(nodes.indexOf(button) > nodes.findIndex((node) => node.type === "AnalysisRunModelPreview"));
  button.props.onClick();
  assert.deepEqual(markingUpdates, [true]);
  nodes.find((node) => node.type === "AnalysisRunRoundImages").props.onFinishEditing();
  assert.deepEqual(markingUpdates, [true, false]);
});

test("a pending round permits inline tip marking while another round trains", () => {
  const RoundDetail = component("components/AnalysisRunRoundDetail.js", {
    react: { useState: () => [false, () => {}] },
    "next/navigation": { useRouter: () => ({ push() {} }) },
    "@/features/Analysis/analysisConfig": { ANALYSIS_MODEL_STATUS_META: {
      alignment_pending: { label: "待相機對齊", tone: "warning" },
    } },
    "@/lib/formatUtils": { formatNumberWithUnit: String },
    "../lib/analysisRunUtils": { analysisRoundStatus: () => ({ label: "待補正", tone: "warning" }) },
    "../hooks/useAnalysisRunRoundRetry": { __esModule: true, default: () => ({ saving: false, retry() {} }) },
  });
  const round = { round_key: "record:mode-1:round.01", status: "alignment_pending" };
  const tree = RoundDetail({ analysisId: "analysis-test", round, busy: true, model: { status: "alignment_pending" }, onReloadRun() {} });
  const nodes = descendants(tree);
  const header = nodes.find((node) => node.type === "SubsectionHeader");
  assert.deepEqual(descendants(header.props.title).map((node) => node.props?.children).filter((value) => typeof value === "string"), ["待補正"]);
  assert.equal(nodes.find((node) => node.type === "AnalysisRunStereoReview"), undefined);
  assert.equal(nodes.find((node) => node.props?.children === "重新自動對齊").props.disabled, true);
  assert.equal(nodes.find((node) => node.type === "Button" && textContent(node) === "標記尖端").props.disabled, false);
});

test("editing a round removes the separate toggle and ends only after a successful save", async () => {
  const RoundDetail = component("components/AnalysisRunRoundDetail.js", {
    react: { useState: () => [true, () => {}] },
    "@/features/Analysis/analysisConfig": { ANALYSIS_MODEL_STATUS_META: {} },
    "@/lib/formatUtils": { formatNumberWithUnit: String },
    "../lib/analysisRunUtils": { analysisRoundStatus: () => ({ label: "完成", tone: "success" }) },
    "../hooks/useAnalysisRunRoundRetry": { __esModule: true, default: () => ({ saving: false }) },
  });
  const row = RoundDetail({ analysisId: "a", round: { round_key: "r", status: "tip_completed" } });
  assert.equal(descendants(row).filter((node) => node.type === "Button").length, 0);
  assert.equal(descendants(row).find((node) => node.type === "AnalysisRunRoundImages").props.marking, true);

  for (const saved of [false, true]) {
    for (const actionElement of [undefined, { id: "fixed-tip-action" }]) {
      let finished = 0;
      const Editor = component("components/AnalysisRunRoundTipEditor.js", {
        "react-dom": { createPortal: (children, target) => ({ type: "portal", props: { children, target } }) },
        "../hooks/useAnalysisRunTipCorrection": { __esModule: true, default: () => ({ points: {}, save: async () => saved }) },
      });
      const editor = Editor({ analysisId: "a", roundKey: "r", views: [], actionElement, onFinishEditing: () => { finished++; } });
      const nodes = descendants(editor);
      const buttons = nodes.filter((node) => node.type === "Button");
      assert.equal(buttons.length, 1);
      assert.equal(textContent(buttons[0]), "儲存尖端");
      if (actionElement) assert.equal(nodes.find((node) => node.type === "portal").props.target, actionElement);
      else assert.equal(nodes.find((node) => node.type === "portal"), undefined);
      await buttons[0].props.onClick();
      assert.equal(finished, saved ? 1 : 0);
    }
  }
});

test("a completed model preview passes the tip coordinates to its 3D viewer", () => {
  const reference = { signature: "model", gaussian_path: "model.ply", geometry_warning: "影像幾何不穩定" };
  const Preview = component("components/AnalysisRunModelPreview.js", {
    "../hooks/useAnalysisRunModelPreview": { __esModule: true, default: () => ({ reference }) },
    "../lib/analysisModelCoordinateUtils": { savedModelTipLandmark, trackedModelTipLandmark },
  });
  const landmark = { x_mm: 10, y_mm: 20, z_mm: 30, valid: false };
  const node = Preview({ analysisId: "analysis-test", model: { status: "completed", model_path: "model.ply" }, landmark });
  const content = node.type(node.props);
  const viewer = descendants(content).find((item) => item.type === "AnalysisRunModelReference");
  assert.equal(viewer.props.landmark, landmark);
  assert.equal(viewer.props.reference, reference);
  assert.equal(descendants(content).find((item) => item.props?.role === "status").props.children, reference.geometry_warning);
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
  assert.deepEqual(nodes.filter((node) => node.type === "AnalysisRunRoundTipImage").map((node) => node.props.view.camera_id), ["top", "side"]);
  const modelNode = nodes.find((node) => node.type === "AnalysisRunRoundTipModel");
  assert.equal(modelNode.props.model, model);
  assert.ok(nodes.indexOf(modelNode) > nodes.findLastIndex((node) => node.type === "AnalysisRunRoundTipImage"));
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

test("the first round initializes in current processing images instead of duplicating the result editor", () => {
  const RoundDetail = component("components/AnalysisRunRoundDetail.js", {
    react: { useState: (value) => [value, () => {}] },
    "@/features/Analysis/analysisConfig": { ANALYSIS_MODEL_STATUS_META: {} },
    "@/lib/formatUtils": { formatNumberWithUnit: String },
    "../lib/analysisRunUtils": { analysisRoundStatus: () => ({ label: "等待初始化", tone: "warning" }) },
    "../hooks/useAnalysisRunRoundRetry": { __esModule: true, default: () => ({ saving: false }) },
  });
  const tree = RoundDetail({ analysisId: "a", round: { round_key: "r", status: "waiting_tip_seed" } });
  assert.equal(descendants(tree).find((node) => node.type === "AnalysisRunRoundImages"), undefined);
  const Processing = component("components/AnalysisRunProcessingImages.js", {});
  const model = { status: "completed", model_path: "model.ply" };
  const initializingRound = { round_key: "r", status: "waiting_tip_seed" };
  const current = descendants(Processing({ analysisId: "a", initializingRound, model })).find(
    (node) => node.type === "AnalysisRunRoundImages",
  );
  assert.equal(current.props.marking, true);
  assert.equal(current.props.model, model);
  const Editor = component("components/AnalysisRunRoundTipEditor.js", {
    "../hooks/useAnalysisRunTipCorrection": { __esModule: true, default: (props) => {
      assert.equal(props.initializing, true);
      assert.equal(props.requireModel, true);
      return { points: {} };
    } },
  });
  assert.ok(descendants(Editor({ analysisId: "a", roundKey: "r", initializing: true, views: [], model })).some(
    (node) => node.type === "AnalysisRunRoundTipModel",
  ));
});

test("round selection shows only that round's content and stays selected through live updates", () => {
  let selection = null;
  const Overview = component("components/AnalysisRunRoundOverview.js", {
    react: {
      useId: () => "round-results",
      useState: () => [selection, (value) => { selection = value; }],
    },
    "@/features/Analysis/analysisConfig": { ANALYSIS_MODEL_STATUS_META: {
      completed: { label: "已完成", tone: "success" },
    } },
    "../lib/analysisRunUtils": { analysisRoundStatus: () => ({ label: "完成" }) },
  });
  const first = { round_key: "mode-1:round.99", round_id: "round.99", mode_id: "mode-1" };
  const second = { round_key: "mode-1:round.300", round_id: "round.300", mode_id: "mode-1" };
  const model = { round_key: second.round_key, status: "completed" };
  const landmark = { round_key: second.round_key, valid: false };
  const correction = { round_key: second.round_key, corrected_tip: { valid: true, x_mm: 2 } };
  const formalData = { rounds: [first, second], models: [model], landmarks: [landmark] };
  const props = { analysisId: "analysis-test", formalData, busy: true, onReloadRun() {} };
  const initial = descendants(Overview(props));
  assert.equal(initial.filter((node) => node.type === "AnalysisRunRoundDetail").length, 1);
  assert.equal(initial.find((node) => node.type === "AnalysisRunRoundDetail").props.round, first);
  const list = initial.find((node) => node.type === "AnalysisRunRoundList");
  assert.deepEqual(list.props.items.map((item) => item.roundId), ["round.99", "round.300"]);
  list.props.onSelect(second.round_key);

  const liveData = { ...formalData, rounds: formalData.rounds.map((round) => ({ ...round })), corrections: [correction] };
  const updated = descendants(Overview({ ...props, formalData: liveData }));
  const detail = updated.find((node) => node.type === "AnalysisRunRoundDetail");
  assert.equal(detail.props.round.round_key, second.round_key);
  assert.equal(detail.props.model, model);
  assert.equal(detail.props.landmark, correction.corrected_tip);
  assert.equal(detail.props.correction, correction);
  assert.equal(detail.props.busy, true);
  assert.equal(detail.props.onReloadRun, props.onReloadRun);
  const panel = updated.find((node) => node.props?.role === "tabpanel");
  assert.equal(panel.key, second.round_key);

  const removed = descendants(Overview({ ...props, formalData: { rounds: [first] } }));
  assert.equal(removed.find((node) => node.type === "AnalysisRunRoundDetail").props.round, first);
  const empty = descendants(Overview({ ...props, formalData: {} }));
  assert.equal(empty.find((node) => node.type === "AnalysisRunRoundDetail"), undefined);
  assert.equal(empty.find((node) => node.type === "AnalysisRunRoundList"), undefined);
  assert.match(empty.map(textContent).join(""), /尚無可顯示的分析輪次/);
});

test("round list supports keyboard selection and scrolls only its own pane to the selected tab", () => {
  const selections = [];
  const focusCalls = [];
  const items = ["round.01", "round.02", "round.03"].map((roundKey) => ({
    roundKey,
    status: { label: "尖端待補標", tone: "warning" },
    modelStatus: { label: "已完成", tone: "success" },
  }));
  const buttons = items.map((_, index) => ({
    focus: (options) => focusCalls.push({ index, options }),
    getBoundingClientRect: () => ({ top: index * 100, bottom: index * 100 + 50 }),
  }));
  const scrollPane = {
    scrollTop: 0,
    getBoundingClientRect: () => ({ top: 0, bottom: 150 }),
    querySelectorAll: () => buttons,
  };
  const List = component("components/AnalysisRunRoundList.js", {
    react: { useRef: () => ({ current: scrollPane }) },
    "@/components/panels/Panel": { StatusPill: "StatusPill" },
  });
  const tree = List({ items, selectedRoundKey: "round.01", idPrefix: "rounds", contentId: "content", onSelect: (key) => selections.push(key) });
  const tabs = descendants(tree).filter((node) => node.props?.role === "tab");
  const statuses = descendants(tabs[0]).filter((node) => node.type === "StatusPill");
  assert.deepEqual(statuses.map((node) => ({ label: textContent(node), tone: node.props.tone })), [items[0].status, items[0].modelStatus]);
  assert.deepEqual(tabs.map((tab) => tab.props.tabIndex), [0, -1, -1]);
  assert.deepEqual(tabs.map((tab) => tab.props["aria-selected"]), [true, false, false]);
  assert.ok(tabs.every((tab) => tab.props["aria-controls"] === "content"));
  assert.equal(new Set(tabs.map((tab) => tab.props.id)).size, items.length);
  let prevented = 0;
  tabs[0].props.onKeyDown({ key: "End", preventDefault() { prevented++; } });
  assert.deepEqual(selections, ["round.03"]);
  assert.deepEqual(focusCalls, [{ index: 2, options: { preventScroll: true } }]);
  assert.equal(scrollPane.scrollTop, 100);
  tabs[2].props.onKeyDown({ key: "ArrowDown", preventDefault() { prevented++; } });
  tabs[0].props.onKeyDown({ key: "ArrowUp", preventDefault() { prevented++; } });
  tabs[2].props.onKeyDown({ key: "Home", preventDefault() { prevented++; } });
  assert.deepEqual(selections, ["round.03", "round.01", "round.03", "round.01"]);
  tabs[1].props.onKeyDown({ key: "Tab", preventDefault() { prevented++; } });
  assert.equal(prevented, 4);
  tabs[1].props.onClick();
  assert.equal(selections.at(-1), "round.02");
});

test("tip correction entry lists only missing tips and can switch back to all rounds", () => {
  let filter = "missing";
  const Overview = component("components/AnalysisRunRoundOverview.js", {
    react: {
      useId: () => "missing-tips",
      useState: (initial) => initial === "missing"
        ? [filter, (value) => { filter = value; }]
        : [initial, () => {}],
    },
    "@/features/Analysis/analysisConfig": { ANALYSIS_MODEL_STATUS_META: {} },
    "../lib/analysisRunUtils": { analysisRoundStatus: () => ({ label: "待補標" }) },
    "@/components/inputs/Input": { SelectInput: "SelectInput" },
  });
  const rounds = ["round.01", "round.02"].map((round_key) => ({ round_key, status: "tip_invalid" }));
  const formalData = { rounds, landmarks: [{ round_key: "round.01", image_tip_confirmed: true, valid: false }] };
  const props = { analysisId: "test", formalData, initialTipFilter: "missing" };
  const initial = descendants(Overview(props));
  assert.deepEqual(initial.find((node) => node.type === "AnalysisRunRoundList").props.items.map((item) => item.roundKey), ["round.02"]);
  assert.equal(initial.find((node) => node.type === "AnalysisRunRoundDetail").props.round.round_key, "round.02");
  initial.find((node) => node.type === "SelectInput").props.onValueChange("all");
  const all = descendants(Overview(props));
  assert.equal(all.find((node) => node.type === "AnalysisRunRoundList").props.items.length, 2);
  const direct = descendants(Overview({ ...props, initialTipFilter: "all", initialRoundKey: "round.02" }));
  assert.equal(direct.find((node) => node.type === "AnalysisRunRoundDetail").props.round.round_key, "round.02");
});

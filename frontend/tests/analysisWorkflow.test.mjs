import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import vm from "node:vm";

import * as runUtils from "../src/features/AnalysisRun/lib/analysisRunUtils.js";
import * as tipResults from "../src/features/AnalysisRun/lib/analysisTipResultsUtils.js";
import * as autoRepairUtils from "../src/features/AnalysisRun/lib/analysisAutoRepairUtils.js";
import * as config from "../src/features/Analysis/analysisConfig.js";
import * as analysisUtils from "../src/features/Analysis/lib/analysisUtils.js";
import { saveAnalysisRoundTip } from "../src/features/AnalysisRun/lib/analysisRoundTipApiUtils.js";

const require = createRequire(import.meta.url);
const swc = require("next/dist/build/swc");
await swc.loadBindings();

function component(filename, overrides = {}) {
  const source = new URL(`../src/features/${filename}`, import.meta.url);
  const { code } = swc.transformSync(readFileSync(source, "utf8"), {
    filename: source.pathname,
    jsc: { parser: { syntax: "ecmascript", jsx: true }, transform: { react: { runtime: "automatic" } } },
    module: { type: "commonjs" },
  });
  const compiled = { exports: {} };
  const dependencies = {
    react: { useEffect() {}, useCallback: (callback) => callback, useState: () => [false, () => {}] },
    "@/components/panels/Panel": { Panel: "Panel", PanelHeader: "PanelHeader", StatusPill: "StatusPill" },
    "@/features/Analysis/analysisConfig": config,
    "../analysisConfig": config,
    "../lib/analysisUtils": analysisUtils,
    "@/features/AnalysisRun/lib/analysisStereoReviewUtils": { needsStereoPoseReview: () => false },
    "@/features/AnalysisRun/lib/analysisRunUtils": runUtils,
    "@/features/AnalysisRun/lib/analysisTipResultsUtils": tipResults,
    "./lib/analysisRunUtils": runUtils,
    "./lib/analysisTipResultsUtils": tipResults,
    "./lib/analysisAutoRepairUtils": autoRepairUtils,
    "./lib/analysisStereoReviewUtils": { needsStereoPoseReview: () => false },
    "@/features/Notifications/hooks/useNotificationsContext": { __esModule: true, default: () => ({ showNotification() {} }) },
    "@/features/MainNavigation/hooks/useAnalysisSecondaryNavigation": { __esModule: true, default() {} },
    "@/lib/formatUtils": { formatDateTime: String },
    ...overrides,
  };
  vm.runInThisContext(`(function(require,module,exports){${code}\n})`)((name) => {
    if (name in dependencies) return dependencies[name];
    if (name === "react/jsx-runtime") return require(name);
    return { __esModule: true, default: name.split("/").at(-1) };
  }, compiled, compiled.exports);
  return compiled.exports.default;
}

function descendants(node) {
  if (!node || typeof node !== "object") return [];
  return [node, ...[node.props?.children].flat(Infinity).flatMap(descendants)];
}

function text(node) {
  if (typeof node === "string") return node;
  if (!node || typeof node !== "object") return "";
  return [node.props?.children].flat(Infinity).map(text).join("");
}

const run = { analysis_id: "test", method_name: "rotating", status: "partially_completed", stage: "completed" };
const data = {
  rounds: [{ round_key: "record:mode:round.01", status: "tip_invalid" }],
  models: [{ round_key: "record:mode:round.01", status: "completed" }],
  landmarks: [{ round_key: "record:mode:round.01", valid: false, image_tip_confirmed: true }],
  corrections: [], trajectory: [], quality: {},
};

test("analysis retains its round workspace and registers page navigation in the header", () => {
  const navigation = [];
  const AnalysisRun = component("AnalysisRun/AnalysisRun.js", {
    "@/features/MainNavigation/hooks/useAnalysisSecondaryNavigation": { __esModule: true, default: (options) => navigation.push(options) },
    "./hooks/useAnalysisRun": { __esModule: true, default: () => ({ run, formalData: data, loading: false }) },
  });
  const tree = AnalysisRun({ analysisId: "test", initialRoundKey: data.rounds[0].round_key });
  const nodes = descendants(tree);
  const workspace = nodes.filter((node) => node.type === "AnalysisRunRoundOverview");
  assert.equal(workspace.length, 1);
  assert.equal(workspace[0].props.formalData, data);
  assert.equal(workspace[0].props.initialRoundKey, data.rounds[0].round_key);
  const header = nodes.find((node) => node.type === "PanelHeader");
  const buttons = descendants(header.props.action).filter((node) => node.type === "Button");
  assert.deepEqual(buttons.map(text), ["重新讀取"]);
  assert.equal(navigation[0].canOpenResults, true);
  assert.equal(navigation[0].navigationLocked, false);
  assert.ok(nodes.some((node) => node.type === "StatusCard" && node.props.title === "尖端標記"));
  assert.ok(!nodes.some((node) => node.type === "FormalTipReview"));
});

test("result page offers charts and export while the shared header owns its record tab", () => {
  const Viewer = component("TrajectoryViewer/FormalTrajectoryViewer.js", {
    "./hooks/useFormalTrajectoryResults": { __esModule: true, default: () => ({
      ...data, run, loading: false, load() {}, downloadExport() {},
    }) },
  });
  const tree = Viewer({ analysisId: "test" });
  const nodes = descendants(tree);
  assert.ok(nodes.some((node) => node.type === "TrajectoryViewerImageTipCharts"));
  assert.ok(!nodes.some((node) => ["TrajectoryViewerModelOutputs", "AnalysisRunRoundOverview", "AnalysisRunRoundTipEditor"].includes(node.type)));
  const header = nodes.find((node) => node.type === "PanelHeader");
  const buttons = descendants(header.props.action).filter((node) => node.type === "Button");
  assert.deepEqual(buttons.map(text), ["重新讀取", "匯出結果"]);
});

test("each analysis list item retains direct actions for its own record", () => {
  const calls = [];
  const Runs = component("Analysis/components/AnalysisDashboardRuns.js");
  const rows = descendants(Runs({
    runs: [run, { ...run, analysis_id: "processing", status: "processing" }],
    exportingIds: new Set(),
    onOpen: (id) => calls.push(["open", id]),
    onResults: (id) => calls.push(["results", id]),
    onExport: (id) => calls.push(["export", id]),
  })).filter((node) => node.type === "li");
  const completedButtons = descendants(rows[0]).filter((node) => node.type === "Button");
  assert.deepEqual(completedButtons.map(text), ["匯出", "查看分析", "查看結果"]);
  completedButtons.find((node) => text(node) === "查看分析").props.onClick();
  completedButtons.find((node) => text(node) === "查看結果").props.onClick();
  const progress = descendants(rows[1]).find((node) => node.type === "Button" && text(node) === "查看進度");
  progress.props.onClick();
  assert.deepEqual(calls, [["open", "test"], ["results", "test"], ["open", "processing"]]);
});

test("paused analysis continues saved work without mixing navigation into execution controls", () => {
  const actions = [];
  const Actions = component("AnalysisRun/components/AnalysisRunActions.js", {
    "../lib/analysisRunUtils": runUtils,
  });
  const tree = Actions({ status: "paused", stage: "linking_tip_trajectory", onAction: (action) => actions.push(action) });
  const buttons = descendants(tree).filter((node) => node.type === "Button");
  assert.ok(buttons.some((node) => text(node) === "繼續分析"));
  assert.ok(!buttons.some((node) => ["開始分析", "查看結果", "返回分析"].includes(text(node))));
  buttons.find((node) => text(node) === "繼續分析").props.onClick();
  assert.deepEqual(actions, ["resume"]);
});

test("the record action row exposes an orange repair button and locks mutations while pending", () => {
  const actions = [];
  const Actions = component("AnalysisRun/components/AnalysisRunActions.js", {
    "../lib/analysisRunUtils": runUtils,
  });
  const props = { status: "partially_completed", autoRepair: { visible: true, disabled: false }, onAction: (action) => actions.push(action) };
  const buttons = descendants(Actions(props)).filter((node) => node.type === "Button");
  const repair = buttons.find((node) => text(node) === "自動修正與對齊");
  assert.equal(repair.props.variant, "warning");
  assert.ok(!repair.props.disabled);
  repair.props.onClick();
  assert.deepEqual(actions, ["auto-repair"]);
  const pending = descendants(Actions({ ...props, pendingAction: "auto-repair", locked: true }));
  assert.ok(pending.some((node) => node.type === "Button" && text(node) === "準備修正中…" && node.props.disabled));
  assert.ok(!descendants(Actions({ ...props, autoRepair: { visible: false } })).some((node) => text(node) === "自動修正與對齊"));
});

test("legacy review URLs redirect to the same analysis workspace without confirming every round", () => {
  const redirects = [];
  const Review = component("TipReview/TipReview.js", {
    "next/navigation": { redirect: (url) => redirects.push(url) },
  });
  Review({ analysisId: "test", initialRoundKey: data.rounds[0].round_key });
  Review({ analysisId: "test" });
  assert.equal(new URL(redirects[0], "http://localhost").searchParams.get("round_key"), data.rounds[0].round_key);
  assert.ok(redirects.every((url) => url.startsWith("/analysis/test?")));
  assert.ok(redirects.every((url) => url.endsWith("#analysis-round-results")));
});

test("inline tip saves retain the original authenticated BFF request and payload", async (context) => {
  const payload = { round_key: data.rounds[0].round_key, observations: [], invalid: false };
  const controller = new AbortController();
  context.mock.method(globalThis, "fetch", async (url, options) => {
    assert.equal(url, "/api/analysis/analysis%20test/tip-corrections");
    assert.equal(options.method, "POST");
    assert.deepEqual(JSON.parse(options.body), payload);
    return Response.json({ correction_id: "saved", round_key: payload.round_key });
  });
  const saved = await saveAnalysisRoundTip("analysis test", payload, controller.signal);
  assert.equal(saved.correction_id, "saved");
});

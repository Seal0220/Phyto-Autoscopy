import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import vm from "node:vm";
import * as config from "../src/features/Analysis/analysisConfig.js";
import * as http from "../src/lib/httpUtils.js";
import { createPageDataCache } from "../src/lib/pageDataCache.js";

const require = createRequire(import.meta.url);
const swc = require("next/dist/build/swc");
await swc.loadBindings();

function load(path, dependencies) {
  const source = new URL(`../src/features/Analysis/${path}`, import.meta.url);
  const { code } = swc.transformSync(readFileSync(source, "utf8"), {
    filename: source.pathname,
    jsc: { parser: { syntax: "ecmascript", jsx: true }, transform: { react: { runtime: "automatic" } } },
    module: { type: "commonjs" },
  });
  const compiled = { exports: {} };
  vm.runInThisContext(`(function(require,module,exports,window){${code}\n})`)((name) => {
    if (name in dependencies) return dependencies[name];
    if (name === "react/jsx-runtime") return require(name);
    return { __esModule: true, default: name.split("/").at(-1) };
  }, compiled, compiled.exports, { clearTimeout });
  return compiled.exports;
}

const utils = load("lib/analysisUtils.js", { "../analysisConfig.js": config });

function harness(api) {
  const cache = createPageDataCache();
  const state = [], refs = [], callbacks = [], effects = [], pending = [];
  let index = 0;
  const changed = (left, right) => !left || left.length !== right.length || right.some((value, i) => value !== left[i]);
  const react = {
    useState(initial) {
      const slot = index++;
      if (!(slot in state)) state[slot] = typeof initial === "function" ? initial() : initial;
      return [state[slot], (value) => { state[slot] = typeof value === "function" ? value(state[slot]) : value; }];
    },
    useRef(initial) {
      const slot = index++;
      refs[slot] ||= { current: initial };
      return refs[slot];
    },
    useCallback(callback, deps) {
      const slot = index++;
      if (changed(callbacks[slot]?.deps, deps)) callbacks[slot] = { deps, callback };
      return callbacks[slot].callback;
    },
    useEffect(callback, deps) {
      const slot = index++;
      if (changed(effects[slot]?.deps, deps)) pending.push(() => {
        effects[slot]?.cleanup?.();
        effects[slot] = { deps, cleanup: callback() };
      });
    },
  };
  const hook = load("hooks/useAnalysisSetup.js", {
    react,
    "@/lib/httpUtils": http,
    "@/hooks/PageDataCacheProvider": { usePageDataCache: () => cache },
    "../analysisConfig": config,
    "../lib/analysisUtils": {
      ...utils,
      validateAnalysisSetupStep() {},
      buildAnalysisCreatePayload: () => ({ record_id: "record", method: "rotating" }),
    },
    "../lib/analysisApiUtils": {
      loadAnalysisSetupOptions: async () => [],
      analysisMutationErrorMessage: (error) => error.message,
      ...api,
    },
  }).default;
  return {
    render() {
      index = 0;
      const value = hook({ initialRecordId: "record" });
      pending.splice(0).forEach((effect) => effect());
      return value;
    },
    unmount: () => effects.forEach((effect) => effect?.cleanup?.()),
  };
}

test("one start action creates a draft and starts it without a validation request", async () => {
  const calls = [];
  const app = harness({
    createAnalysisRun: async () => { calls.push("create"); return { analysis_id: "analysis", status: "draft" }; },
    startAnalysisRun: async (id) => { calls.push(`start:${id}`); return { analysis_id: id, status: "validating" }; },
  });
  const run = await app.render().startRun();
  assert.deepEqual(calls, ["create", "start:analysis"]);
  assert.equal(run.status, "validating");
  assert.equal(app.render().createdRun.analysis_id, "analysis");
  assert.equal(app.render().mutationPending, "");
  app.unmount();
});

test("a known start failure reuses the created draft and blocks concurrent starts", async () => {
  let finish, creations = 0, starts = 0;
  const app = harness({
    createAnalysisRun: async () => { creations++; return { analysis_id: "analysis", status: "draft" }; },
    startAnalysisRun: () => {
      starts++;
      return starts === 1 ? new Promise((_, reject) => { finish = reject; }) : Promise.resolve({ status: "processing" });
    },
  });
  const hook = app.render();
  const first = hook.startRun();
  assert.equal(await hook.startRun(), false);
  finish(new Error("啟動失敗"));
  assert.equal(await first, false);
  assert.equal(app.render().createdRun.status, "draft");
  assert.equal((await app.render().startRun()).analysis_id, "analysis");
  assert.equal(creations, 1);
  assert.equal(starts, 2);
  app.unmount();
});

test("an uncertain start cannot be repeated and an unmounted completion cannot navigate", async () => {
  let starts = 0;
  const app = harness({
    createAnalysisRun: async () => ({ analysis_id: "analysis" }),
    startAnalysisRun: async () => { starts++; throw new http.UnknownMutationOutcomeError("結果不確定"); },
  });
  assert.equal(await app.render().startRun(), false);
  assert.equal(app.render().mutationRequiresRefresh, true);
  assert.equal(await app.render().startRun(), false);
  assert.equal(starts, 1);
  app.unmount();

  let finish;
  const late = harness({
    createAnalysisRun: () => new Promise((resolve) => { finish = resolve; }),
    startAnalysisRun: () => assert.fail("must not start after unmount"),
  });
  const request = late.render().startRun();
  late.unmount();
  finish({ analysis_id: "late" });
  assert.equal(await request, false);
});

function descendants(node) {
  if (!node || typeof node !== "object") return [];
  return [node, ...[node.props?.children].flat(Infinity).flatMap(descendants)];
}

test("the single start button opens progress directly after a successful start", async () => {
  const routes = [];
  const screen = load("AnalysisNew.js", {
    react: { useEffect() {} },
    "next/navigation": { useRouter: () => ({ push: (route) => routes.push(route) }) },
    "@/features/Notifications/hooks/useNotificationsContext": { __esModule: true, default: () => ({ showNotification() {} }) },
    "@/features/MainNavigation/hooks/useAnalysisSecondaryNavigation": { __esModule: true, default() {} },
    "./analysisConfig": config,
    "./hooks/useAnalysisSetup": { __esModule: true, default: () => ({
      sources: [], setup: { recordId: "record" }, currentStep: 4, highestStep: 4,
      startRun: async () => ({ analysis_id: "analysis:1", status: "validating" }),
    }) },
  }).default;
  const buttons = descendants(screen({})).filter((node) => node.type === "Button");
  const start = buttons.filter((node) => [node.props.children].flat().includes("開始分析"));
  assert.equal(start.length, 1);
  assert.equal(buttons.some((node) => [node.props.children].flat().includes("驗證分析")), false);
  start[0].props.onClick();
  await new Promise((resolve) => setImmediate(resolve));
  assert.deepEqual(routes, ["/analysis/analysis%3A1"]);
});

import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import vm from "node:vm";

import {
  createPageDataCache,
  PAGE_CACHE_INVALIDATED_EVENT,
  PAGE_CACHE_MAX_AGE_MS,
} from "../src/lib/pageDataCache.js";
import * as pageDataCache from "../src/lib/pageDataCache.js";
import * as http from "../src/lib/httpUtils.js";
import * as runUtils from "../src/features/AnalysisRun/lib/analysisRunUtils.js";
import * as analysisUtils from "../src/features/Analysis/lib/analysisUtils.js";
import * as settingsUtils from "../src/features/Settings/lib/settingsUtils.js";
import * as settingsEvents from "../src/lib/settingsEvents.js";
import * as scheduleConfig from "../src/features/Schedule/scheduleConfig.js";
import * as scheduleUtils from "../src/features/Schedule/lib/scheduleUtils.js";
import { requestAnalysisResource } from "../src/features/AnalysisRun/lib/analysisRunApiUtils.js";
import { loadUnifiedCalibrationWorkspace } from "../src/features/Calibration/lib/unifiedCalibrationApiUtils.js";

const require = createRequire(import.meta.url);
const swc = require("next/dist/build/swc");
await swc.loadBindings();
const settle = () => new Promise((resolve) => setImmediate(resolve));

function hookHarness(filename, cache, dependencies = {}) {
  const source = new URL(`../src/${filename}`, import.meta.url);
  const { code } = swc.transformSync(readFileSync(source, "utf8"), {
    filename: source.pathname,
    jsc: { parser: { syntax: "ecmascript" } },
    module: { type: "commonjs" },
  });
  const slots = [], pending = [], timers = new Map();
  let cursor = 0, timerId = 0, snapshot;
  const changed = (previous, next) => !previous
    || next.some((value, index) => !Object.is(value, previous[index]));
  const react = {
    useState(initial) {
      const index = cursor++;
      slots[index] ||= { value: typeof initial === "function" ? initial() : initial };
      return [slots[index].value, (value) => {
        slots[index].value = typeof value === "function" ? value(slots[index].value) : value;
      }];
    },
    useRef(initial) {
      const index = cursor++;
      return slots[index] ||= { current: initial };
    },
    useCallback(callback, dependencies) {
      const index = cursor++;
      if (changed(slots[index]?.dependencies, dependencies)) {
        slots[index] = { callback, dependencies };
      }
      return slots[index].callback;
    },
    useEffect(callback, dependencies) {
      const index = cursor++;
      if (changed(slots[index]?.dependencies, dependencies)) pending.push(() => {
        slots[index]?.cleanup?.();
        slots[index] = { dependencies, cleanup: callback() };
      });
    },
  };
  const compiled = { exports: {} };
  const imports = {
    react,
    "@/hooks/PageDataCacheProvider": { usePageDataCache: () => cache },
    "@/hooks/PhytoSocketProvider": { usePhytoSocketContext: () => ({ snapshot }) },
    "@/lib/httpUtils": http,
    "@/lib/pageDataCache": pageDataCache,
    "@/features/Settings/lib/settingsUtils": settingsUtils,
    "../lib/analysisRunUtils": runUtils,
    "../lib/analysisUtils": analysisUtils,
    ...dependencies,
  };
  const window = {
    setInterval: (callback) => { timers.set(++timerId, callback); return timerId; },
    clearInterval: (id) => timers.delete(id),
    clearTimeout,
    setTimeout,
  };
  vm.runInNewContext(code, {
    require: (name) => {
      if (!(name in imports)) throw new Error(`Missing test dependency: ${name}`);
      return imports[name];
    },
    module: compiled, exports: compiled.exports,
    window, document: { visibilityState: "visible", addEventListener() {}, removeEventListener() {} },
    AbortController, Blob, structuredClone, fetch: (...args) => globalThis.fetch(...args),
  });
  return {
    render(props = {}) {
      cursor = 0;
      const state = compiled.exports.default(props);
      pending.splice(0).forEach((effect) => effect());
      return state;
    },
    setSnapshot(value) { snapshot = value; },
    poll() { timers.forEach((callback) => callback()); },
    unmount() { slots.forEach((slot) => slot?.cleanup?.()); },
  };
}

test("fresh navigation reads expire without losing the last successful snapshot", () => {
  let now = 1000;
  const cache = createPageDataCache({ now: () => now });
  const original = { value: [1] };
  cache.write("analysis:a", original);
  original.value.push(2);
  assert.deepEqual(cache.read("analysis:a").value, { value: [1] });
  now += PAGE_CACHE_MAX_AGE_MS - 1;
  assert.equal(cache.read("analysis:a").fresh, true);
  cache.update("analysis:a", (data) => ({ ...data, progress: 0.5 }));
  now += 1;
  assert.equal(cache.read("analysis:a").fresh, false);
  assert.equal(cache.read("analysis:a").value.progress, 0.5);
});

test("bounded cache retains recently visited pages and blocks reads started before invalidation", () => {
  const cache = createPageDataCache({ maxEntries: 2 });
  cache.write("analysis:a", 1);
  cache.write("records:list", 2);
  cache.read("analysis:a");
  cache.write("analysis:b", 3);
  assert.equal(cache.read("records:list"), null);
  const version = cache.version;
  cache.invalidate("analysis:a", { discard: true });
  assert.equal(cache.write("analysis:a", 9, version), false);
  assert.equal(cache.read("analysis:a"), null);
  assert.equal(cache.read("analysis:b").fresh, true);
  cache.clear();
  assert.equal(cache.read("analysis:b"), null);
});

const run = { analysis_id: "test", status: "completed", progress: 1 };
const bundle = { run, progress: { ...run }, formalData: { rounds: [{ round_key: "round.1" }] } };

test("analysis remount uses cached rounds without rereading, while explicit refresh still reaches the API", async () => {
  const cache = createPageDataCache();
  let reads = 0;
  const dependencies = {
    "../lib/analysisRunApiUtils": {
      async loadAnalysisRunBundle() { reads += 1; return bundle; },
    },
  };
  const first = hookHarness("features/AnalysisRun/hooks/useAnalysisRun.js", cache, dependencies);
  first.render({ analysisId: "test" });
  await settle();
  assert.equal(first.render({ analysisId: "test" }).formalData.rounds.length, 1);
  first.unmount();
  const second = hookHarness("features/AnalysisRun/hooks/useAnalysisRun.js", cache, dependencies);
  second.setSnapshot({ analysis: bundle.progress });
  const restored = second.render({ analysisId: "test" });
  assert.equal(restored.loading, false);
  assert.equal(restored.formalData.rounds.length, 1);
  await settle();
  assert.equal(reads, 1, "an unchanged socket snapshot must not trigger another full read");
  await restored.load();
  assert.equal(reads, 2);
  second.unmount();
});

test("stale results remain visible during background updates, failed reads can retry, and analysis IDs stay isolated", async () => {
  let now = 0, reads = 0, finish;
  const cache = createPageDataCache({ now: () => now });
  cache.write("analysis:results:test", { run, trajectory: [{ x: 1 }] });
  now = PAGE_CACHE_MAX_AGE_MS;
  const screen = hookHarness("features/TrajectoryViewer/hooks/useFormalTrajectoryResults.js", cache, {
    "../lib/formalTrajectoryApiUtils": {
      loadFormalTrajectoryResults() { reads += 1; return new Promise((resolve, reject) => { finish = { resolve, reject }; }); },
    },
  });
  const restored = screen.render({ analysisId: "test" });
  assert.equal(restored.loading, false);
  assert.equal(restored.trajectory[0].x, 1);
  assert.equal(reads, 1);
  finish.reject(new Error("讀取失敗"));
  await settle();
  const failed = screen.render({ analysisId: "test" });
  assert.equal(failed.trajectory[0].x, 1);
  assert.match(failed.loadError, /讀取失敗/);
  const retry = failed.load();
  finish.resolve({ run, trajectory: [{ x: 2 }] });
  await retry;
  assert.equal(cache.read("analysis:results:test").value.trajectory[0].x, 2);
  const different = screen.render({ analysisId: "another" });
  assert.equal(different.run, null);
  assert.deepEqual(Array.from(different.trajectory), []);
  screen.unmount();
  finish.resolve({ run: { ...run, analysis_id: "another" }, trajectory: [{ x: 99 }] });
  await settle();
  assert.equal(cache.read("analysis:results:another"), null);
});

test("active analysis polling still fetches and updates progress after a fresh cache restore", async () => {
  const cache = createPageDataCache();
  const active = { ...run, status: "processing", progress: 0.5 };
  cache.write("analysis:run:test", { ...bundle, run: active, progress: active });
  let polls = 0;
  const screen = hookHarness("features/AnalysisRun/hooks/useAnalysisRun.js", cache, {
    "../lib/analysisRunApiUtils": {
      async loadAnalysisRunBundle() { throw new Error("Unexpected full reload"); },
      async loadAnalysisProgress() { polls += 1; return { ...active, progress: 0.6 }; },
    },
  });
  screen.render({ analysisId: "test" });
  screen.poll();
  await settle();
  assert.equal(polls, 1);
  assert.equal(screen.render({ analysisId: "test" }).progress.progress, 0.6);
  assert.equal(cache.read("analysis:run:test").value.progress.progress, 0.6);
  screen.unmount();
});

test("cached dashboard and records render immediately without duplicate entry reads", async () => {
  const cache = createPageDataCache();
  cache.write("analysis:dashboard", { sources: [{ record_id: "r" }], runs: [run] });
  cache.write("records:list", [{ record_id: "r" }]);
  const dashboard = hookHarness("features/Analysis/hooks/useAnalysisDashboard.js", cache, {
    "../lib/analysisApiUtils": { loadAnalysisDashboard() { throw new Error("Unexpected dashboard read"); } },
    "@/features/AnalysisRun/lib/analysisRunApiUtils": {},
  });
  assert.equal(dashboard.render().runs.length, 1);
  const records = hookHarness("features/RecordsStorage/hooks/useRecordsStorage.js", cache);
  assert.equal(records.render().records[0].record_id, "r");
  await settle();
  assert.equal(dashboard.render().loadError, "");
  assert.equal(records.render().loadError, "");
  dashboard.unmount();
  records.unmount();
});

test("unsaved setting edits never become another page's cached committed settings", () => {
  const cache = createPageDataCache();
  cache.write("settings:cameras", { cameras: { top: { gain: 2 } } });
  const first = hookHarness("hooks/useSettings.js", cache);
  const props = { group: "cameras", open: true };
  first.render(props).updateField(["cameras", "top", "gain"], 9);
  assert.equal(first.render(props).payload.cameras.top.gain, 9);
  first.unmount();
  const second = hookHarness("hooks/useSettings.js", cache);
  assert.equal(second.render(props).payload.cameras.top.gain, 2);
  assert.equal(second.render(props).loading, false);
  second.unmount();
});

test("manual tip mutation invalidates cached analysis before and after both success and unknown failure", async () => {
  const originalWindow = globalThis.window, originalFetch = globalThis.fetch;
  const cache = createPageDataCache();
  const events = [];
  globalThis.window = new EventTarget();
  window.addEventListener(PAGE_CACHE_INVALIDATED_EVENT, (event) => {
    events.push(event.detail.prefix);
    cache.invalidate(event.detail.prefix, event.detail);
  });
  try {
    cache.write("analysis:results:test", { trajectory: [{ x: 1 }] });
    fetch = async () => {
      assert.equal(cache.read("analysis:results:test"), null);
      cache.write("analysis:results:test", { trajectory: [{ x: 1 }] });
      return Response.json({ applied: true });
    };
    await requestAnalysisResource("/api/analysis/test/tip-corrections", { method: "POST", body: {} });
    assert.equal(cache.read("analysis:results:test"), null);
    assert.deepEqual(events, ["analysis:", "analysis:"]);
    cache.write("analysis:results:test", { trajectory: [{ x: 1 }] });
    fetch = async () => { throw new TypeError("Connection lost"); };
    await assert.rejects(requestAnalysisResource("/api/analysis/test/tip-corrections", { method: "POST" }), /尚未確認/);
    assert.equal(cache.read("analysis:results:test"), null);
  } finally {
    globalThis.window = originalWindow;
    globalThis.fetch = originalFetch;
  }
});

test("calibration catalog reuse still reads fresh requester lock ownership with no HTTP cache", async () => {
  const originalFetch = globalThis.fetch;
  const requests = [];
  try {
    globalThis.fetch = async (path, options) => {
      requests.push({ path, cache: options.cache });
      return Response.json({ lock_owned_by_requester: false });
    };
    const catalog = [[{ board_id: "board" }], [], [], []];
    const [status, boards] = await loadUnifiedCalibrationWorkspace(undefined, { catalog });
    assert.equal(status.lock_owned_by_requester, false);
    assert.deepEqual(boards, catalog[0]);
    assert.deepEqual(requests, [{ path: "/api/calibration/status", cache: "no-store" }]);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("socket changes invalidate results off-page without repeatedly invalidating unchanged progress", () => {
  const cache = createPageDataCache();
  cache.write("analysis:run:test", bundle);
  cache.write("analysis:results:test", { run, trajectory: [] });
  const sync = hookHarness("hooks/usePageDataCacheSync.js", cache);
  sync.render({ analysis: { ...bundle.progress, results_revision: "new" } });
  assert.equal(cache.read("analysis:results:test").fresh, false);
  const version = cache.version;
  sync.render({ analysis: { ...bundle.progress, results_revision: "new" } });
  assert.equal(cache.version, version);
  sync.unmount();
});

test("capture schedule defaults reuse committed setting snapshots when returning to capture", () => {
  const cache = createPageDataCache();
  cache.write("settings:schedule", { schedule: { duration_seconds: 11, rotation_enabled: true } });
  cache.write("settings:cameras", { cameras: { rotating: { arm_height_mm: 555 } } });
  const schedule = hookHarness("features/Schedule/hooks/useSchedule.js", cache, {
    "@/lib/settingsEvents": settingsEvents,
    "../scheduleConfig": scheduleConfig,
    "../lib/scheduleUtils": scheduleUtils,
  });
  schedule.render();
  const restored = schedule.render();
  assert.equal(restored.defaultsLoading, false);
  assert.equal(restored.defaultsLoadError, "");
  assert.equal(restored.schedule.duration_seconds, "11");
  assert.equal(restored.schedule.arm_height_mm, 555);
  schedule.unmount();
});

test("capture activity marks record and source caches stale while retaining displayable data", () => {
  const cache = createPageDataCache();
  cache.write("records:list", [{ record_id: "r" }]);
  cache.write("analysis:sources", [{ record_id: "r" }]);
  const sync = hookHarness("hooks/usePageDataCacheSync.js", cache);
  sync.render({ schedule: { record_id: "r", status: "running", capture_count: 1 } });
  assert.equal(cache.read("records:list").fresh, true);
  sync.render({ schedule: { record_id: "r", status: "running", capture_count: 2 } });
  assert.equal(cache.read("records:list").fresh, false);
  assert.equal(cache.read("analysis:sources").fresh, false);
  assert.equal(cache.read("records:list").value[0].record_id, "r");
  sync.unmount();
});

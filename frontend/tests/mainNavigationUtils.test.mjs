import assert from "node:assert/strict";
import test from "node:test";

import {
  CAPTURE_SECONDARY_NAVIGATION_ITEMS,
  MAIN_NAVIGATION_ITEMS,
} from "../src/features/MainNavigation/mainNavigationConfig.js";
import {
  isMainNavigationItemActive,
  isSecondaryNavigationItemActive,
  secondaryNavigationGroups,
} from "../src/features/MainNavigation/lib/mainNavigationUtils.js";

test("main navigation exposes calibration beside analysis", () => {
  assert.deepEqual(
    MAIN_NAVIGATION_ITEMS.map((item) => [item.href, item.label]),
    [
      ["/capture", "捕捉"],
      ["/analysis", "分析"],
      ["/calibration", "校正"],
      ["/models", "模型"],
    ],
  );
  assert.equal(CAPTURE_SECONDARY_NAVIGATION_ITEMS.length, 5);
});

test("main navigation matches its route and nested feature pages", () => {
  assert.equal(isMainNavigationItemActive("/capture", "/capture"), true);
  assert.equal(isMainNavigationItemActive("/analysis/run-1", "/analysis"), true);
  assert.equal(isMainNavigationItemActive("/calibration", "/calibration"), true);
  assert.equal(isMainNavigationItemActive("/models/", "/models"), true);
});

test("main navigation does not match adjacent or prefixed routes", () => {
  assert.equal(isMainNavigationItemActive("/analysis-tools", "/analysis"), false);
  assert.equal(isMainNavigationItemActive("/capture", "/analysis"), false);
  assert.equal(isMainNavigationItemActive(undefined, "/capture"), false);
  assert.equal(isMainNavigationItemActive("/", ""), false);
});
test("analysis overview and creation always show the same fixed navigation without a record group", () => {
  for (const path of ["/analysis", "/analysis/new"]) {
    const groups = secondaryNavigationGroups(path);
    assert.equal(groups.length, 1);
    assert.deepEqual(groups[0].items.map((item) => [item.label, item.href]), [
      ["總覽", "/analysis"],
      ["新增分析", "/analysis/new"],
    ]);
  }
});

test("opened records add a separate analysis and results group with encoded IDs", () => {
  const run = secondaryNavigationGroups("/analysis/a%3A1", { canOpenResults: true });
  assert.equal(run.length, 2);
  assert.deepEqual(run[0].items.map((item) => item.label), ["總覽", "新增分析"]);
  assert.deepEqual(run[1].items.map((item) => [item.label, item.href]), [
    ["分析紀錄", "/analysis/a%3A1"],
    ["分析結果", "/analysis/a%3A1/results"],
  ]);
  const results = secondaryNavigationGroups("/analysis/a%3A1/results");
  assert.deepEqual(results[1].items.map((item) => item.href), ["/analysis/a%3A1", "/analysis/a%3A1/results"]);
  assert.equal(results[1].items.at(-1).disabled, false);
  assert.equal(isSecondaryNavigationItemActive("/analysis/a%3A1/results", "/analysis/a%3A1/results"), true);
  assert.equal(isSecondaryNavigationItemActive("/analysis/new", "/analysis"), false);
  assert.equal(isSecondaryNavigationItemActive("/analysis/a%3A1", "/analysis/a%3A1#analysis-round-results"), false);
});

test("record readiness and mutation locks still restrict navigation without changing fixed labels", () => {
  const run = secondaryNavigationGroups("/analysis/test", { canOpenResults: true, navigationLocked: true, resultsLocked: true });
  assert.equal(run.flatMap((group) => group.items).every((item) => item.disabled), true);
  const notReady = secondaryNavigationGroups("/analysis/test");
  assert.equal(notReady[1].items[0].disabled, false);
  assert.equal(notReady[1].items[1].disabled, true);
  assert.deepEqual(secondaryNavigationGroups("/analysis-other"), []);
  assert.ok(secondaryNavigationGroups("/capture")[0].items.some((item) => item.href === "/capture#schedule"));
});

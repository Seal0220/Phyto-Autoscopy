import assert from "node:assert/strict";
import test from "node:test";

import {
  CAPTURE_SECONDARY_NAVIGATION_ITEMS,
  MAIN_NAVIGATION_ITEMS,
} from "../src/features/MainNavigation/mainNavigationConfig.js";
import { isMainNavigationItemActive } from "../src/features/MainNavigation/lib/mainNavigationUtils.js";

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

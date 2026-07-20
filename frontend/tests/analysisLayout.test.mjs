import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

function source(path) {
  return readFileSync(
    new URL(`../src/features/Analysis/${path}`, import.meta.url),
    "utf8",
  );
}

test("analysis creation keeps source warnings in global notifications", () => {
  const analysisNew = source("AnalysisNew.js");
  const sourcesStep = source("components/AnalysisSetupSourcesStep.js");

  assert.match(analysisNew, /showNotification\(stepError, "warning"\)/);
  assert.match(analysisNew, /showNotification\(message, "warning"\)/);
  assert.doesNotMatch(analysisNew, /<RetryMessage/);
  assert.doesNotMatch(sourcesStep, /preview\?\.(?:errors|warnings).*map/);
  assert.doesNotMatch(sourcesStep, /role="alert"/);
});

test("available records scroll inside the first analysis setup step", () => {
  const dashboard = source("Analysis.js");
  const records = source("components/AnalysisAvailableRecords.js");
  const sourcesStep = source("components/AnalysisSetupSourcesStep.js");

  assert.match(sourcesStep, /<AnalysisAvailableRecords/);
  assert.match(records, /max-h-80/);
  assert.match(records, /overflow-y-auto/);
  assert.doesNotMatch(dashboard, /title="可分析紀錄"/);
});

test("image directories render without a nested panel surface", () => {
  const sourcesStep = source("components/AnalysisSetupSourcesStep.js");

  assert.doesNotMatch(sourcesStep, /InnerPanel/);
  assert.match(sourcesStep, /title="影像目錄"/);
});

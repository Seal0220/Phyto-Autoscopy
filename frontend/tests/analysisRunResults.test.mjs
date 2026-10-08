import assert from "node:assert/strict";
import test from "node:test";

import { loadAnalysisRunBundle } from "../src/features/AnalysisRun/lib/analysisRunApiUtils.js";

test("round results display the latest manual position and retain uncorrected rounds", async (context) => {
  const original = [
    { round_key: "round.01", valid: false, x_mm: null },
    { round_key: "round.02", valid: true, x_mm: 8 },
  ];
  const corrected = { round_key: "round.01", valid: true, x_mm: 4, manually_corrected: true };
  const responses = new Map([
    ["/api/analysis/test", { analysis_id: "test", status: "partially_completed" }],
    ["/api/analysis/test/progress", { analysis_id: "test", progress: 1 }],
    ["/api/analysis/test/rounds", []],
    ["/api/analysis/test/round-models", []],
    ["/api/analysis/test/tip-landmarks", original],
    ["/api/analysis/test/tip-trajectory", []],
    ["/api/analysis/test/tip-corrections", [
      { round_key: "round.01", corrected_tip: { ...corrected, x_mm: 2 } },
      { round_key: "round.01", corrected_tip: corrected },
    ]],
  ]);
  context.mock.method(globalThis, "fetch", async (path) => {
    assert.equal(responses.has(path), true, `unexpected request: ${path}`);
    return new Response(JSON.stringify(responses.get(path)));
  });
  const result = await loadAnalysisRunBundle("test");
  assert.deepEqual(result.formalData.landmarks, [corrected, original[1]]);
  assert.equal(original[0].valid, false);
});

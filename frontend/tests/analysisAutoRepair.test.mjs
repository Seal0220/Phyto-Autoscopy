import assert from "node:assert/strict";
import test from "node:test";

import { analysisAutoRepairAvailability } from "../src/features/AnalysisRun/lib/analysisAutoRepairUtils.js";
import { performAnalysisRunAction } from "../src/features/AnalysisRun/lib/analysisRunApiUtils.js";

const run = { status: "partially_completed", stage: "completed" };
const round = { round_key: "one", status: "tip_completed" };
const landmark = { round_key: "one", valid: true };
const model = { round_key: "one", status: "completed" };
const data = { rounds: [round], models: [model], landmarks: [landmark], corrections: [] };

test("only unresolved failures and pending alignment expose repair", () => {
  assert.equal(analysisAutoRepairAvailability(run, data).visible, false);
  assert.equal(analysisAutoRepairAvailability({ ...run, status: "failed" }, data).visible, true);
  for (const status of ["failed", "alignment_pending", "model_failed", "tip_invalid", "tip_only"]) {
    const faulty = { ...data, rounds: [{ ...round, status }], landmarks: [{ ...landmark, valid: false }] };
    assert.equal(analysisAutoRepairAvailability(run, faulty).visible, true, status);
  }
  assert.equal(analysisAutoRepairAvailability(run, { ...data, models: [{ ...model, status: "failed" }] }).visible, true);
  assert.equal(analysisAutoRepairAvailability(run, { ...data, corrections: [{ round_key: "one", pending_alignment: true }] }).visible, true);
});

test("manual exclusions and corrected tips do not trigger repair from stale tip status", () => {
  const faulty = { ...data, rounds: [{ ...round, status: "tip_invalid" }], landmarks: [{ ...landmark, valid: false }] };
  for (const correction of [{ invalid: true }, { corrected_tip: landmark }]) {
    assert.equal(analysisAutoRepairAvailability(run, { ...faulty, corrections: [{ round_key: "one", ...correction }] }).visible, false);
  }
});

test("repair is visible but disabled during training or initial tip seeding", () => {
  const faulty = { ...data, rounds: [{ ...round, status: "alignment_pending" }] };
  for (const status of ["processing", "reconstructing", "validating", "pausing"]) {
    const available = analysisAutoRepairAvailability({ ...run, status }, faulty);
    assert.equal(available.visible, true);
    assert.equal(available.disabled, true);
  }
  assert.equal(analysisAutoRepairAvailability({ status: "paused", stage: "waiting_for_tip_seed" }, faulty).disabled, true);
  assert.equal(analysisAutoRepairAvailability({ status: "paused" }, faulty).disabled, false);
  assert.equal(analysisAutoRepairAvailability({ status: "needs_review", stage: "waiting_for_model_review" }, data).visible, true);
});

test("repair uses one scoped authenticated BFF mutation", async (context) => {
  const requests = [];
  context.mock.method(globalThis, "fetch", async (url, options) => {
    requests.push([url, options.method, JSON.parse(options.body)]);
    return Response.json({ analysis_id: "test", status: "processing" });
  });
  await performAnalysisRunAction("test", "auto-repair");
  assert.deepEqual(requests, [["/api/analysis/test/auto-repair", "POST", {}]]);
});

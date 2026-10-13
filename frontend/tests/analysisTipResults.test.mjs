import assert from "node:assert/strict";
import test from "node:test";

import {
  analysisRoundResultsUrl,
  analysisTipResults,
} from "../src/features/AnalysisRun/lib/analysisTipResultsUtils.js";
import {
  imageTipPlotLayout,
  imageTipTrajectorySeries,
} from "../src/features/TrajectoryViewer/lib/imageTipTrajectoryUtils.js";

const rounds = [1, 2, 3, 4].map((number) => ({
  round_key: `record:mode-1:round.${number}`,
  round_id: `round.${number}`, mode_id: "mode-1", status: "tip_invalid",
}));

function imageTip(index) {
  return {
    round_key: rounds[index].round_key, image_tip_confirmed: true, valid: false,
    image_observations: [
      { view_id: `mode-1:${rounds[index].round_id}:snapshot.01:top:123`, x_px: 100 + index, y_px: 200 },
      { view_id: `mode-1:${rounds[index].round_id}:snapshot.01:side:124`, x_px: 300 + index, y_px: 400 },
    ],
  };
}

test("confirmed image tips do not need manual marking when metric registration is missing", () => {
  const summary = analysisTipResults(rounds, [imageTip(0), imageTip(2)]);
  assert.equal(summary.markedCount, 2);
  assert.equal(summary.metricCount, 0);
  assert.deepEqual(summary.pendingRounds.map((item) => item.round_id), ["round.2", "round.4"]);
});

test("latest saved correction resolves the queue and an explicit invalid tip remains skipped", () => {
  const manual = { ...imageTip(1), manually_corrected: true };
  const summary = analysisTipResults(rounds, [imageTip(0)], [
    { round_key: manual.round_key, corrected_tip: { ...manual, image_tip_confirmed: false } },
    { round_key: manual.round_key, corrected_tip: manual },
    { round_key: rounds[2].round_key, invalid: true },
  ]);
  assert.equal(summary.markedCount, 2);
  assert.equal(summary.resolved.get(manual.round_key), manual);
  assert.deepEqual(summary.pendingRounds.map((item) => item.round_id), ["round.4"]);
  assert.deepEqual(analysisTipResults([{ ...rounds[0], status: "reconstructing" }]).pendingRounds, []);
});

test("legacy review links go to inline round results with safely encoded selection", () => {
  const route = analysisRoundResultsUrl("analysis_003", rounds[1].round_key, { missingTips: true });
  const url = new URL(route, "http://localhost");
  assert.equal(url.pathname, "/analysis/analysis_003");
  assert.equal(url.searchParams.get("round_key"), rounds[1].round_key);
  assert.equal(url.searchParams.has("tip_filter"), false);
  assert.equal(url.hash, "#analysis-round-results");
  assert.equal(new URL(analysisRoundResultsUrl("analysis_003", undefined, { missingTips: true }), url).searchParams.get("tip_filter"), "missing");
});

test("image trajectories retain camera-specific coordinates and gaps without using model points", () => {
  const summary = analysisTipResults(rounds, [imageTip(0), imageTip(2), imageTip(3)]);
  const top = imageTipTrajectorySeries(rounds, summary.resolved, "top");
  const side = imageTipTrajectorySeries(rounds, summary.resolved, "side");
  assert.deepEqual(top.map((segment) => segment.points.map((point) => point.roundId)), [["round.1"], ["round.3", "round.4"]]);
  assert.equal(top[0].points[0].x_px, 100);
  assert.equal(side[0].points[0].x_px, 300);
  const layout = imageTipPlotLayout(top);
  assert.ok(Math.abs(
    (layout.projectY(201) - layout.projectY(200)) - (layout.projectX(101) - layout.projectX(100)),
  ) < 1e-10);
  assert.equal(imageTipPlotLayout([]), null);
  const bad = { ...imageTip(0), image_observations: [{ camera_id: "top", x_px: null, y_px: 3 }] };
  assert.deepEqual(imageTipTrajectorySeries(rounds, new Map([[bad.round_key, bad]]), "top"), []);
});

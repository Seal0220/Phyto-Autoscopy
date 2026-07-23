import assert from "node:assert/strict";
import test from "node:test";

import {
  analysisDefaultSelectedModeIds,
  analysisMethodFromCameraSources,
  analysisRecordSummaryItems,
  analysisSetupFromRecord,
  analysisSourcesFromPayload,
  buildAnalysisCreatePayload,
  createInitialAnalysisSetup,
  validateAnalysisSetupStep,
} from "../src/features/Analysis/lib/analysisUtils.js";

const modes = [
  {
    id: "ContinuousInterval.01",
    type: "continuous_interval",
    folder: "ContinuousInterval.01",
    image_count: 30,
  },
  {
    id: "AngleInterval.01",
    type: "angle_interval",
    folder: "AngleInterval.01",
    image_count: 90,
  },
];

function readySetup() {
  const setup = analysisSetupFromRecord(
    createInitialAnalysisSetup(),
    {
      record_id: "record-1",
      record_path: "C:/captures/record-1",
      available_modes: modes,
    },
  );
  setup.sourcePreview = {
    ready: true,
    ready_round_count: 1,
    intrinsics_readiness: {
      top: { ready: true },
      side: { ready: true },
      rotating: { ready: true },
    },
    aruco_readiness: { ready: true },
    backend_readiness: { available: true },
  };
  return setup;
}

test("選擇紀錄會帶入根目錄並預設排除連續擷取模式", () => {
  const setup = readySetup();

  assert.equal(setup.recordId, "record-1");
  assert.equal(setup.recordPath, "C:/captures/record-1");
  assert.deepEqual(setup.selectedModeIds, ["AngleInterval.01"]);
  assert.equal(setup.method, "round_multiview");
});

test("分析方法只依旋臂視角旗標推導", () => {
  assert.equal(
    analysisMethodFromCameraSources({
      rotating: { enabled: true },
    }),
    "round_multiview",
  );
  assert.equal(
    analysisMethodFromCameraSources({
      rotating: { enabled: false },
    }),
    "top_side_tip_only",
  );
});

test("來源資料會正規化模式與總張數", () => {
  const [source] = analysisSourcesFromPayload({
    sources: [{
      record_id: "record-1",
      record_path: "C:/captures/record-1",
      total_image_count: "120",
      available_modes: modes,
    }],
  });

  assert.equal(source.total_image_count, 120);
  assert.equal(source.available_modes.length, 2);
  assert.deepEqual(
    analysisDefaultSelectedModeIds(source.available_modes),
    ["AngleInterval.01"],
  );
});

test("四個建立步驟可驗證完整 Round 分析配置", () => {
  const setup = readySetup();

  for (const step of [1, 2, 3, 4]) {
    assert.equal(validateAnalysisSetupStep(setup, step), true);
  }
});

test("建立 payload 不包含舊影格範圍、偏移或 ROI", () => {
  const payload = buildAnalysisCreatePayload(readySetup());
  const serialized = JSON.stringify(payload);

  assert.equal(payload.method, "round_multiview");
  assert.deepEqual(payload.mode_ids, ["AngleInterval.01"]);
  assert.equal(payload.camera_sources.top.enabled, true);
  assert.equal(payload.camera_sources.side.enabled, true);
  assert.equal(payload.camera_sources.rotating.enabled, true);
  for (const forbidden of [
    "start_frame",
    "end_frame",
    "frame_offset",
    "manual_frame_offset",
    "top_roi",
    "side_roi",
    "plant_base",
    "mog2",
  ]) {
    assert.equal(serialized.includes(forbidden), false);
  }
});

test("紀錄摘要只列出時間、模式數量與總張數", () => {
  const items = analysisRecordSummaryItems({
    created_at: "2026-07-22T08:00:00Z",
    ended_at: "2026-07-22T09:00:00Z",
    available_modes: modes,
    total_image_count: 120,
  });

  assert.deepEqual(
    items.map((item) => item.label),
    ["開始時間", "結束時間", "模式數量", "總張數"],
  );
  assert.equal(items[2].value, "2 種");
  assert.equal(items[3].value, "120 張");
});

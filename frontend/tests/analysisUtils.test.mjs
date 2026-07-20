import assert from "node:assert/strict";
import test from "node:test";

import {
  analysisDefaultEndFrame,
  analysisMethodFromCameraSources,
  analysisProgressPercent,
  analysisSetupFromRecord,
  analysisSourcesFromPayload,
  activeCalibrationFromPayload,
  buildAnalysisCreatePayload,
  createInitialAnalysisSetup,
  mergeAnalysisProgress,
  mergeAnalysisRuns,
  validateAnalysisSetupStep,
} from "../src/features/Analysis/lib/analysisUtils.js";

test("record auto-fill derives the method from rotating availability", () => {
  const initial = createInitialAnalysisSetup();
  const populated = analysisSetupFromRecord(initial, {
    record_id: "record-auto",
    total_frame_count: 8,
    camera_directories: {
      top: "record-auto/top",
      side: "record-auto/side",
      rotating: "record-auto/rotating",
    },
  });

  assert.equal(populated.recordId, "record-auto");
  assert.equal(populated.endFrame, "8");
  assert.equal(populated.method, "top_side_rotating");
  assert.equal(populated.cameraSources.rotating.enabled, true);
  assert.equal(
    analysisMethodFromCameraSources({
      rotating: {
        enabled: false,
      },
    }),
    "top_side",
  );
});

function validSetup() {
  const setup = createInitialAnalysisSetup("record-1");
  setup.cameraSources.top.path = "session-1/top";
  setup.cameraSources.side.path = "session-1/side";
  setup.sourcePreview = {
    ready: true,
    total_frame_count: 12,
    pairable_frame_count: 12,
    camera_resolutions: {
      top: [1280, 960],
      side: [1280, 960],
      rotating: null,
    },
    errors: [],
  };
  setup.calibrationId = "calibration-1";
  setup.endFrame = "12";
  setup.topRoi = {
    x: "0",
    y: "1",
    width: "640",
    height: "480",
  };
  setup.sideRoi = {
    x: "2",
    y: "3",
    width: "640",
    height: "480",
  };
  setup.parameters = {
    ...setup.parameters,
    segmentationHistory: "100",
    segmentationVarianceThreshold: "16",
    segmentationLearningRate: "-1",
    segmentationInitializationFrames: "10",
    openingKernelSize: "3",
    closingKernelSize: "5",
    erosionKernelSize: "3",
    minimumTopContourArea: "0",
    minimumSideContourArea: "0",
    lightingChangeArea: "0",
    lightingChangeEstimateFrames: "5",
    topPlantBaseX: "0",
    topPlantBaseY: "240",
    topSelectedPoints: "3",
    topRoiUpdateMargin: "0",
    sidePlantBaseX: "0",
    sidePlantBaseY: "470",
    sideSelectedPoints: "4",
    sideRoiUpdateMargin: "0",
    maximumEpipolarDistance: "5.5",
    minimumPathConnectivity: "8",
    maximumInterpolationGapSeconds: "30",
  };
  return setup;
}

const sources = [
  {
    record_id: "record-1",
    ready: true,
    total_frame_count: 12,
    camera_resolutions: {
      top: [1280, 960],
      side: [1280, 960],
    },
    not_ready_reasons: [],
  },
];
const activeCalibration = {
  calibration_id: "calibration-1",
  valid: true,
  image_width: 1280,
  image_height: 960,
};

test("analysis dashboard normalizes source wrappers and nested runs", () => {
  const normalized = analysisSourcesFromPayload({
    sources: [
      {
        record_id: "record-1",
        ready: true,
        top_frame_count: "4",
        side_frame_count: 3,
        total_frame_count: 5,
        pairable_frame_count: 3,
        camera_resolutions: {
          top: [1920, 1080],
          side: [1280, 720],
        },
        analysis_runs: [
          {
            analysis_id: "analysis-1",
            progress: 1.4,
          },
        ],
      },
    ],
  });

  assert.equal(normalized[0].top_frame_count, 4);
  assert.equal(normalized[0].total_frame_count, 5);
  assert.deepEqual(normalized[0].camera_resolutions, {
    top: [1920, 1080],
    side: [1280, 720],
    rotating: null,
  });
  assert.equal(normalized[0].analysis_runs[0].progress, 1);
  assert.throws(
    () => analysisSourcesFromPayload({ sources: null }),
    /可分析紀錄資料格式錯誤/,
  );
});

test("analysis range defaults to every frame-pair row, not only usable pairs", () => {
  assert.equal(analysisDefaultEndFrame({
    total_frame_count: 8,
    pairable_frame_count: 5,
  }), "8");
  assert.equal(analysisDefaultEndFrame({
    total_frame_count: 0,
    pairable_frame_count: 5,
  }), "");
});

test("analysis runs merge without duplicating embedded runs", () => {
  const merged = mergeAnalysisRuns(
    [
      {
        analysis_runs: [
          {
            analysis_id: "analysis-1",
            status: "draft",
          },
        ],
      },
    ],
    [
      {
        analysis_id: "analysis-1",
        status: "processing",
      },
      {
        analysis_id: "analysis-2",
        status: "completed",
      },
    ],
  );

  assert.equal(merged.length, 2);
  assert.equal(
    merged.find((run) => run.analysis_id === "analysis-1").status,
    "processing",
  );
});

test("analysis websocket progress updates only its matching dashboard run", () => {
  const runs = [
    {
      analysis_id: "analysis-1",
      status: "processing",
      progress: 0.1,
    },
    {
      analysis_id: "analysis-2",
      status: "draft",
      progress: 0,
    },
  ];
  const next = mergeAnalysisProgress(runs, {
    analysis_id: "analysis-1",
    status: "processing",
    stage: "detecting_top_tip",
    progress: 0.75,
    current_frame: 15,
    total_frames: 20,
    last_error: null,
  });

  assert.equal(next[0].progress, 0.75);
  assert.equal(next[0].current_frame, 15);
  assert.equal(next[0].stage, "detecting_top_tip");
  assert.equal(next[1], runs[1]);
  assert.equal(mergeAnalysisProgress(runs, {
    analysis_id: null,
    status: "idle",
  }), runs);
});

test("analysis setup requires scanned sources and valid calibration", () => {
  const setup = validSetup();

  assert.equal(validateAnalysisSetupStep(setup, 4, activeCalibration), true);
  setup.sourcePreview = {
    ready: false,
    errors: ["缺少側視影像"],
  };
  assert.throws(
    () => validateAnalysisSetupStep(setup, 1, activeCalibration),
    /缺少側視影像/,
  );
  setup.sourcePreview = validSetup().sourcePreview;
  assert.throws(
    () => validateAnalysisSetupStep(
      setup,
      1,
      { ...activeCalibration, valid: false },
    ),
    /啟用的相機校正無效/,
  );
});

test("analysis parameter validation rejects even morphology kernels", () => {
  const setup = validSetup();
  setup.parameters.openingKernelSize = "4";

  assert.throws(
    () => validateAnalysisSetupStep(setup, 3, activeCalibration),
    /核心大小必須是正奇數/,
  );
});

test("analysis range stays within source frames and analysis image bounds", () => {
  const tooManyFrames = validSetup();
  tooManyFrames.endFrame = "13";
  assert.throws(
    () => validateAnalysisSetupStep(
      tooManyFrames,
      2,
      activeCalibration,
    ),
    /不可超過此紀錄的 12 組影格/,
  );

  const outsideImage = validSetup();
  outsideImage.topRoi.x = "1000";
  outsideImage.topRoi.width = "640";
  assert.throws(
    () => validateAnalysisSetupStep(
      outsideImage,
      2,
      activeCalibration,
    ),
    /俯視 ROI 不可超出 1280 × 960/,
  );
});

test("analysis ROI uses capture resolution even when calibration resolution differs", () => {
  const setup = validSetup();
  setup.topRoi.x = "1000";
  setup.topRoi.width = "640";
  setup.sourcePreview = {
    ...setup.sourcePreview,
    camera_resolutions: {
      top: [1920, 1080],
      side: [800, 600],
      rotating: null,
    },
  };

  assert.equal(
    validateAnalysisSetupStep(
      setup,
      2,
      activeCalibration,
    ),
    true,
  );

  setup.sideRoi.x = "700";
  setup.sideRoi.width = "200";
  assert.throws(
    () => validateAnalysisSetupStep(
      setup,
      2,
      activeCalibration,
    ),
    /側視 ROI 不可超出 800 × 600 的分析影像範圍/,
  );
});

test("analysis setup preserves explicitly disabled optional cleanup", () => {
  const setup = validSetup();
  setup.parameters.openingKernelSize = "";
  setup.parameters.closingKernelSize = "";
  setup.parameters.erosionKernelSize = "";
  setup.parameters.topUpdateRoi = false;
  setup.parameters.topRoiUpdateMargin = "";
  setup.parameters.sideUpdateRoi = false;
  setup.parameters.sideRoiUpdateMargin = "";

  assert.equal(validateAnalysisSetupStep(setup, 3, activeCalibration), true);

  const payload = buildAnalysisCreatePayload(setup);
  assert.equal(payload.parameters.segmentation.opening_kernel_size, null);
  assert.equal(payload.parameters.segmentation.closing_kernel_size, null);
  assert.equal(payload.parameters.segmentation.erosion_kernel_size, null);
  assert.equal(payload.parameters.top_detection.update_roi, false);
  assert.equal(payload.parameters.top_detection.roi_update_margin_px, null);
  assert.equal(payload.parameters.side_detection.update_roi, false);
  assert.equal(payload.parameters.side_detection.roi_update_margin_px, null);
});

test("analysis payload keeps the selected method and unified camera sources", () => {
  const setup = validSetup();
  setup.parameters.highReprojectionErrorThreshold = "999";
  const payload = buildAnalysisCreatePayload(setup);

  assert.equal(payload.record_id, "record-1");
  assert.equal(payload.manual_frame_offset, 0);
  assert.deepEqual(payload.top_roi, {
    x: 0,
    y: 1,
    width: 640,
    height: 480,
  });
  assert.equal(
    payload.parameters.method.name,
    "top_side",
  );
  assert.equal(payload.method, "top_side");
  assert.deepEqual(payload.camera_sources, setup.cameraSources);
  assert.equal(payload.parameters.segmentation.method, "mog2");
  assert.equal(payload.parameters.side_detection.minimum_path_connectivity, 8);
  assert.equal(
    payload.parameters.side_detection.minimum_path_edge_weight,
    "inverse_distance_transform",
  );
  assert.equal(payload.parameters.interpolation.method, "linear");
  assert.equal(payload.parameters.reprojection.high_error_threshold_px, 10);
});

test("advanced analysis requires rotating source, angle preview, and calibration", () => {
  const setup = validSetup();
  setup.method = "top_side_rotating";
  setup.cameraSources.rotating = {
    enabled: true,
    path: "session-1/rotating",
  };
  setup.sourcePreview = {
    ...setup.sourcePreview,
    rotating_frame_count: 12,
    rotating_angle_count: 12,
    rotating_pairable_frame_count: 12,
    camera_resolutions: {
      ...setup.sourcePreview.camera_resolutions,
      rotating: [1280, 960],
    },
  };

  assert.throws(
    () => validateAnalysisSetupStep(setup, 1, activeCalibration),
    /包含旋臂幾何/,
  );
  assert.throws(
    () => validateAnalysisSetupStep(setup, 1, null),
    /沒有已啟用的相機校正/,
  );
  assert.equal(
    validateAnalysisSetupStep(
      setup,
      1,
      { ...activeCalibration, supports_rotating: true },
    ),
    true,
  );
});

test("manual directories create an analysis without a record ID", () => {
  const setup = validSetup();
  setup.recordId = "";
  setup.cameraSources.top.path = "D:/dataset/top";
  setup.cameraSources.side.path = "D:/dataset/side";

  const payload = buildAnalysisCreatePayload(setup);

  assert.equal(payload.record_id, null);
  assert.equal(payload.camera_sources.top.path, "D:/dataset/top");
  assert.equal(payload.camera_sources.side.path, "D:/dataset/side");
});

test("analysis reads only the active calibration adapter and clamps progress", () => {
  assert.equal(
    activeCalibrationFromPayload({
      calibration_id: "c1",
      valid: true,
    }).valid,
    true,
  );
  assert.equal(activeCalibrationFromPayload(null), null);
  assert.equal(analysisProgressPercent(-1), 0);
  assert.equal(analysisProgressPercent(0.258), 26);
  assert.equal(analysisProgressPercent(4), 100);
});

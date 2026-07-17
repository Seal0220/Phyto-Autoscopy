export const ANALYSIS_METHODS = {
  top_side: {
    label: "頂+側",
    description: "保留原論文的俯視與側視偵測、極線約束及雙目三角測量。",
    reference: "Ruiz-Melero et al. 2024",
  },
  top_side_rotating: {
    label: "頂+側+環繞",
    description: "以頂+側建立基準三維點，再使用 rotating 視角進行穩健多視角精修。",
    reference: "Ruiz-Melero et al. 2024 + rotating multiview refinement",
  },
};

export const HIGH_REPROJECTION_ERROR_THRESHOLD_PX = 10;

export const ANALYSIS_SETUP_STEPS = [
  {
    id: 1,
    label: "影像目錄",
  },
  {
    id: 2,
    label: "校正",
  },
  {
    id: 3,
    label: "分析範圍",
  },
  {
    id: 4,
    label: "方法參數",
  },
  {
    id: 5,
    label: "建立分析",
  },
];

export const ANALYSIS_STATUS_META = {
  draft: {
    label: "草稿",
    tone: "neutral",
  },
  validating: {
    label: "驗證中",
    tone: "warning",
  },
  ready: {
    label: "可開始",
    tone: "success",
  },
  processing: {
    label: "分析中",
    tone: "warning",
  },
  needs_review: {
    label: "等待人工修正",
    tone: "warning",
  },
  reviewing: {
    label: "人工修正中",
    tone: "warning",
  },
  reconstructing: {
    label: "三維重建中",
    tone: "warning",
  },
  completed: {
    label: "已完成",
    tone: "success",
  },
  failed: {
    label: "失敗",
    tone: "offline",
  },
  cancelled: {
    label: "已取消",
    tone: "neutral",
  },
};

export const ANALYSIS_STAGE_LABELS = {
  validating: "驗證輸入資料",
  pairing_frames: "配對雙目影格",
  calibrating: "套用相機校正",
  initializing_background: "初始化背景模型",
  detecting_top_tip: "偵測俯視尖端",
  detecting_side_tip: "偵測側視尖端",
  interpolating: "補足缺失位置",
  waiting_for_review: "等待人工修正",
  triangulating: "計算三維位置",
  calculating_reprojection_error: "計算重投影誤差",
  exporting: "輸出分析結果",
  completed: "已完成",
};

export const ANALYSIS_PARAMETER_DEFAULTS = {
  segmentationHistory: "",
  segmentationVarianceThreshold: "",
  segmentationLearningRate: "",
  segmentationInitializationFrames: "",
  segmentationDetectShadows: false,
  openingKernelSize: "",
  closingKernelSize: "",
  erosionKernelSize: "",
  minimumTopContourArea: "",
  minimumSideContourArea: "",
  lightingChangeArea: "",
  lightingChangeEstimateFrames: "",
  topPlantBaseX: "",
  topPlantBaseY: "",
  topSelectedPoints: "",
  topUpdateRoi: true,
  topRoiUpdateMargin: "",
  sidePlantBaseX: "",
  sidePlantBaseY: "",
  sideSelectedPoints: "",
  sideUpdateRoi: true,
  sideRoiUpdateMargin: "",
  maximumEpipolarDistance: "",
  minimumPathConnectivity: "",
  maximumInterpolationGapSeconds: "",
};

export const MOG2_PARAMETER_FIELDS = [
  {
    key: "segmentationHistory",
    label: "背景歷史影格數",
    min: 1,
    step: 1,
    suffix: "影格",
  },
  {
    key: "segmentationVarianceThreshold",
    label: "變異門檻",
    min: 0.01,
    step: 0.01,
  },
  {
    key: "segmentationLearningRate",
    label: "學習率",
    min: -1,
    max: 1,
    step: 0.01,
  },
  {
    key: "segmentationInitializationFrames",
    label: "背景初始化影格數",
    min: 1,
    step: 1,
    suffix: "影格",
  },
];

export const MORPHOLOGY_PARAMETER_FIELDS = [
  {
    key: "openingKernelSize",
    label: "開運算核心",
    min: 1,
    step: 2,
    suffix: "px",
    description: "填入正奇數以啟用；留空即停用。",
    optional: true,
  },
  {
    key: "closingKernelSize",
    label: "閉運算核心",
    min: 1,
    step: 2,
    suffix: "px",
    description: "填入正奇數以啟用；留空即停用。",
    optional: true,
  },
  {
    key: "erosionKernelSize",
    label: "侵蝕核心",
    min: 1,
    step: 2,
    suffix: "px",
    description: "填入正奇數以啟用；留空即停用。",
    optional: true,
  },
  {
    key: "minimumTopContourArea",
    label: "俯視最小輪廓面積",
    min: 0,
    step: 1,
    suffix: "px²",
  },
  {
    key: "minimumSideContourArea",
    label: "側視最小輪廓面積",
    min: 0,
    step: 1,
    suffix: "px²",
  },
];

export const LIGHTING_PARAMETER_FIELDS = [
  {
    key: "lightingChangeArea",
    label: "光照切換面積門檻",
    min: 0,
    step: 1,
    suffix: "px²",
  },
  {
    key: "lightingChangeEstimateFrames",
    label: "光照穩定等待",
    min: 1,
    step: 1,
    suffix: "影格",
  },
];

export const TOP_DETECTION_PARAMETER_FIELDS = [
  {
    key: "topPlantBaseX",
    label: "俯視植物基部 X",
    min: 0,
    step: 1,
    suffix: "px",
  },
  {
    key: "topPlantBaseY",
    label: "俯視植物基部 Y",
    min: 0,
    step: 1,
    suffix: "px",
  },
  {
    key: "topSelectedPoints",
    label: "俯視候選輪廓數",
    min: 1,
    step: 1,
  },
  {
    key: "topRoiUpdateMargin",
    label: "俯視 ROI 更新邊距",
    min: 0,
    step: 1,
    suffix: "px",
    enabledBy: "topUpdateRoi",
  },
];

export const SIDE_DETECTION_PARAMETER_FIELDS = [
  {
    key: "sidePlantBaseX",
    label: "側視植物基部 X",
    min: 0,
    step: 1,
    suffix: "px",
  },
  {
    key: "sidePlantBaseY",
    label: "側視植物基部 Y",
    min: 0,
    step: 1,
    suffix: "px",
  },
  {
    key: "sideSelectedPoints",
    label: "側視候選輪廓數",
    min: 1,
    step: 1,
  },
  {
    key: "sideRoiUpdateMargin",
    label: "側視 ROI 更新邊距",
    min: 0,
    step: 1,
    suffix: "px",
    enabledBy: "sideUpdateRoi",
  },
  {
    key: "maximumEpipolarDistance",
    label: "Epipolar 最大距離",
    min: 0.01,
    step: 0.01,
    suffix: "px",
  },
];

export const MINIMUM_PATH_CONNECTIVITY_OPTIONS = [
  {
    value: "",
    label: "請選擇",
  },
  {
    value: "4",
    label: "4 鄰接",
  },
  {
    value: "8",
    label: "8 鄰接",
  },
];

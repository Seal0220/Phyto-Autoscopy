export const ANALYSIS_METHODS = {
  fixed: {
    label: "雙鏡頭尖端分析",
    description: "使用俯視與側視影像建立三維尖端標記與跨輪軌跡，不宣稱建立完整環繞模型。",
    version: "2.0.0",
  },
  rotating: {
    label: "每輪多視角三維重建",
    description: "俯視、側視與同一輪的全部有效旋臂視角共同建立三維模型與尖端標記。",
    version: "1.0.0",
  },
};

export const ANALYSIS_CAMERA_LABELS = {
  top: "俯視角",
  side: "側視角",
  rotating: "旋臂視角",
};

export const ARUCO_SAMPLE_STATUS_META = {
  resolved: {
    label: "抽樣定位成功",
    tone: "success",
  },
  partial: {
    label: "部分抽樣成功",
    tone: "warning",
  },
  markers_detected: {
    label: "已偵測，定位失敗",
    tone: "warning",
  },
  markers_missing: {
    label: "未偵測到基準",
    tone: "warning",
  },
  unavailable: {
    label: "無法抽樣",
    tone: "error",
  },
};

export const ANALYSIS_SETUP_STEPS = [
  {
    id: 1,
    label: "選擇紀錄",
  },
  {
    id: 2,
    label: "配置設定",
  },
  {
    id: 3,
    label: "重建與尖端分析",
  },
  {
    id: 4,
    label: "確認並建立",
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
    label: "等待人工確認",
    tone: "warning",
  },
  reviewing: {
    label: "人工確認中",
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
  partially_completed: {
    label: "部分完成",
    tone: "warning",
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
  grouping_rounds: "整理分析輪次",
  snapshotting_intrinsics: "固化相機內參",
  undistorting_images: "套用內參並去畸變",
  detecting_aruco: "偵測 ArUco 基準",
  estimating_camera_poses: "估算相機姿態",
  refining_camera_poses: "精修相機姿態",
  selecting_reconstruction_views: "選擇模型影像",
  extracting_features: "提取多視角特徵",
  matching_features: "配對多視角特徵",
  initializing_round_geometry: "建立初始三維幾何",
  detecting_tip_candidates: "偵測尖端候選",
  reconstructing_round_model: "建立每輪三維模型",
  isolating_plant_model: "分離植物模型",
  extracting_model_point_cloud: "建立植物點雲",
  extracting_model_skeleton: "建立植物骨架",
  triangulating_tip_marker: "計算三維尖端標記",
  refining_tip_marker: "精修尖端標記",
  linking_tip_trajectory: "建立尖端標記軌跡",
  waiting_for_review: "等待人工確認",
  calculating_quality_metrics: "計算品質指標",
  exporting: "輸出分析結果",
  completed: "已完成",
};

export const RECONSTRUCTION_QUALITY_OPTIONS = [
  {
    value: "preview",
    label: "預覽",
  },
  {
    value: "standard",
    label: "標準",
  },
  {
    value: "high",
    label: "高品質",
  },
];

export const RECONSTRUCTION_BACKEND_LABELS = {
  gsplat_3dgs: "gsplat 三維 Gaussian",
  graphdeco_3dgs: "Graphdeco 研究對照",
};

export const ANALYSIS_MODEL_STATUS_META = {
  processing: {
    label: "建立中",
    tone: "warning",
  },
  completed: {
    label: "已完成",
    tone: "success",
  },
  postprocessing_failed: {
    label: "植物後處理失敗",
    tone: "warning",
  },
  failed: {
    label: "建立失敗",
    tone: "offline",
  },
  cancelled: {
    label: "已取消",
    tone: "neutral",
  },
};

export const RECONSTRUCTION_QUALITY_LABELS = Object.fromEntries(
  RECONSTRUCTION_QUALITY_OPTIONS.map((option) => [
    option.value,
    option.label,
  ]),
);

export const ANALYSIS_PARAMETER_DEFAULTS = {
  reconstructionBackend: "gsplat_3dgs",
  qualityPreset: "standard",
  useBundleAdjustment: true,
  generatePlantMask: true,
  usePlantMaskInLoss: true,
  preserveSceneModel: true,
  exportPlantModel: true,
  saveBackgroundModel: false,
  minimumTipConfidence: "0.7",
  minimumSupportingViews: "2",
  maximumTipReprojectionError: "5",
  useSkeletonRefinement: true,
  useTemporalPrior: true,
  waitForLowConfidenceReview: true,
  exportAll2dCandidates: false,
  saveReprojectionOverlays: true,
  saveGaussianModel: true,
  exportScenePointCloud: true,
  exportPlantPointCloud: true,
  exportSkeleton: true,
  exportTipMarkers: true,
  exportTrajectoryCsv: true,
  saveModelPreviews: true,
  saveDiagnostics: true,
  saveCheckpoints: true,
};

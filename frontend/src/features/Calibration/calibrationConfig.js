export const CALIBRATION_PAPER_BASELINE = Object.freeze({
  reference: "Ruiz-Melero et al. 2024",
  individualPattern: Object.freeze([10, 7]),
  individualBoardSizeCm: Object.freeze([59.4, 84.1]),
  stereoBoardSizeCm: Object.freeze([42.0, 59.4]),
});

export const CALIBRATION_CREATE_DEFAULTS = Object.freeze({
  patternColumns: "10",
  patternRows: "7",
  squareSizeMmX: "",
  squareSizeMmY: "",
  stereoPatternColumns: "",
  stereoPatternRows: "",
  stereoSquareSizeMmX: "",
  stereoSquareSizeMmY: "",
  individualBoardWidthCm: "",
  individualBoardHeightCm: "",
  stereoBoardWidthCm: "",
  stereoBoardHeightCm: "",
  worldOrigin: "花盆或植物基部中心",
  worldXAxis: "水平方向",
  worldYAxis: "水平深度方向",
  worldZAxis: "垂直向上",
  worldTransformMatrix: Object.freeze([
    Object.freeze(["1", "0", "0", "0"]),
    Object.freeze(["0", "1", "0", "0"]),
    Object.freeze(["0", "0", "1", "0"]),
    Object.freeze(["0", "0", "0", "1"]),
  ]),
  worldTransformConfirmed: false,
  notes: "",
});

export const CALIBRATION_STATUS = Object.freeze({
  draft: {
    label: "待偵測角點",
    tone: "neutral",
  },
  corners_detected: {
    label: "角點已偵測",
    tone: "warning",
  },
  intrinsics_solved: {
    label: "單目校正完成",
    tone: "warning",
  },
  stereo_solved: {
    label: "雙目校正完成",
    tone: "warning",
  },
  rotating_solved: {
    label: "環繞幾何校正完成",
    tone: "warning",
  },
  valid: {
    label: "有效",
    tone: "success",
  },
  potentially_invalid: {
    label: "可能失效",
    tone: "warning",
  },
  invalid: {
    label: "無效",
    tone: "offline",
  },
  failed: {
    label: "失敗",
    tone: "offline",
  },
});

export const CALIBRATION_WORKFLOW_STEPS = Object.freeze([
  {
    key: "corners",
    label: "偵測棋盤角點",
    pendingLabel: "偵測角點中…",
  },
  {
    key: "intrinsics",
    label: "計算單目校正",
    pendingLabel: "計算單目校正中…",
  },
  {
    key: "stereo",
    label: "計算雙目校正",
    pendingLabel: "計算雙目校正中…",
  },
  {
    key: "rotating",
    label: "計算環繞幾何",
    pendingLabel: "計算環繞幾何中…",
  },
  {
    key: "validate",
    label: "驗證校正資料",
    pendingLabel: "驗證校正中…",
  },
]);

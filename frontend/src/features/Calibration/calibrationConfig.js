export const CALIBRATION_CAMERAS = Object.freeze([
  Object.freeze({
    id: "top",
    label: "俯視角",
    device: "CHLOROCULUS EYE-TOP",
  }),
  Object.freeze({
    id: "side",
    label: "側視角",
    device: "CHLOROCULUS EYE-SIDE",
  }),
  Object.freeze({
    id: "rotating",
    label: "旋臂視角",
    device: "CHLOROCULUS EYE-ARM",
  }),
]);

export const CALIBRATION_CAMERA_MODEL_OPTIONS = Object.freeze([
  Object.freeze({
    value: "auto",
    label: "自動比較模型",
  }),
  Object.freeze({
    value: "opencv",
    label: "OpenCV 標準模型",
  }),
  Object.freeze({
    value: "opencv_rational",
    label: "OpenCV Rational 模型",
  }),
  Object.freeze({
    value: "opencv_fisheye",
    label: "OpenCV Fisheye 模型",
  }),
]);

export const CALIBRATION_SUGGESTED_ANGLES = Object.freeze([
  0,
  45,
  90,
  135,
  180,
  225,
  270,
  315,
]);

export const CALIBRATION_PAPER_SIZE_OPTIONS = Object.freeze([
  Object.freeze({
    value: "a3",
    label: "A3（297 × 420 mm）",
    widthMm: 297,
    heightMm: 420,
  }),
  Object.freeze({
    value: "a4",
    label: "A4（210 × 297 mm）",
    widthMm: 210,
    heightMm: 297,
  }),
  Object.freeze({
    value: "a5",
    label: "A5（148 × 210 mm）",
    widthMm: 148,
    heightMm: 210,
  }),
  Object.freeze({
    value: "letter",
    label: "Letter（215.9 × 279.4 mm）",
    widthMm: 215.9,
    heightMm: 279.4,
  }),
]);

export const CALIBRATION_PAPER_ORIENTATION_OPTIONS = Object.freeze([
  Object.freeze({
    value: "landscape",
    label: "橫向",
  }),
  Object.freeze({
    value: "portrait",
    label: "直向",
  }),
]);

export const CALIBRATION_BOARD_DEFAULTS = Object.freeze({
  paperSize: "a4",
  paperOrientation: "landscape",
  squaresX: "8",
  squaresY: "6",
  printMarginMm: 10,
  markerToSquareRatio: 11 / 15,
});

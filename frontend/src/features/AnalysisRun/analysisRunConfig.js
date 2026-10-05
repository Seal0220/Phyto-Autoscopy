export const ANALYSIS_IMAGE_SPACE_OPTIONS = [
  { value: "source", label: "原始影像" },
  { value: "undistorted", label: "去畸變影像" },
  { value: "reprojection", label: "尖端重投影" },
];

export const ANALYSIS_IMAGE_SPACE_LABELS = {
  source: "原始影像",
  undistorted: "去畸變影像",
  reprojection: "尖端重投影",
};

export const ANALYSIS_VALIDATION_STAGES = new Set([
  "validating",
  "validating_images",
  "verifying_input_files",
  "checking_reconstruction_environment",
  "validation_completed",
]);

export const ANALYSIS_PROGRESS_UNITS = {
  validating_images: "筆",
  verifying_input_files: "張",
  checking_reconstruction_environment: "項",
  validation_completed: "張",
  undistorting_images: "張",
  estimating_stereo_pose: "組",
  waiting_for_stereo_review: "組",
};

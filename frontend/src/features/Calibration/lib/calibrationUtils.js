import {
  CALIBRATION_CREATE_DEFAULTS,
  CALIBRATION_PAPER_BASELINE,
  CALIBRATION_STATUS,
} from "../calibrationConfig.js";

function finiteNumber(
  value,
  label,
) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) {
    throw new Error(`${label}必須是有效數字。`);
  }
  return parsed;
}

function positiveNumber(
  value,
  label,
) {
  const parsed = finiteNumber(
    value,
    label,
  );
  if (parsed <= 0) {
    throw new Error(`${label}必須大於 0。`);
  }
  return parsed;
}

function integerAtLeastTwo(
  value,
  label,
) {
  const parsed = finiteNumber(
    value,
    label,
  );
  if (!Number.isInteger(parsed) || parsed < 2) {
    throw new Error(`${label}必須是至少 2 的整數。`);
  }
  return parsed;
}

function dot(
  first,
  second,
) {
  return first.reduce(
    (total, value, index) => total + value * second[index],
    0,
  );
}

function determinant3(matrix) {
  return (
    matrix[0][0] * (
      matrix[1][1] * matrix[2][2]
      - matrix[1][2] * matrix[2][1]
    )
    - matrix[0][1] * (
      matrix[1][0] * matrix[2][2]
      - matrix[1][2] * matrix[2][0]
    )
    + matrix[0][2] * (
      matrix[1][0] * matrix[2][1]
      - matrix[1][1] * matrix[2][0]
    )
  );
}

function near(
  first,
  second,
  tolerance = 0.000001,
) {
  return Math.abs(first - second) <= tolerance;
}

export function createCalibrationDraft() {
  return {
    ...CALIBRATION_CREATE_DEFAULTS,
    topImagePaths: [],
    sideImagePaths: [],
    rotatingImages: [],
    stereoImagePairs: [],
    worldTransformMatrix: CALIBRATION_CREATE_DEFAULTS.worldTransformMatrix.map(
      (row) => [...row],
    ),
  };
}

export function isValidCalibrationId(value) {
  return typeof value === "string"
    && value.length >= 1
    && value.length <= 160
    && /^[A-Za-z0-9._-]+$/.test(value);
}

export function sourceImagesFromPayload(payload) {
  if (!Array.isArray(payload)) return [];
  return payload.filter((image) => (
    image
    && typeof image === "object"
    && typeof image.path === "string"
    && image.path.trim()
  ));
}

export function calibrationProfilesFromPayload(payload) {
  if (Array.isArray(payload)) return payload;
  return Array.isArray(payload?.profiles) ? payload.profiles : [];
}

export function calibrationStatus(status) {
  return CALIBRATION_STATUS[status] || {
    label: status ? `未知狀態：${status}` : "狀態未知",
    tone: "neutral",
  };
}

export function toggleCalibrationPath(
  paths,
  path,
) {
  return paths.includes(path)
    ? paths.filter((value) => value !== path)
    : [...paths, path];
}

export function appendStereoPair(
  pairs,
  topPath,
  sidePath,
) {
  if (!topPath || !sidePath) {
    throw new Error("請先選擇一張俯視角與一張側視角影像。");
  }
  if (topPath === sidePath) {
    throw new Error("雙鏡頭校正的俯視角與側視角影像不得是同一檔案。");
  }
  if (pairs.some((pair) => pair[0] === topPath && pair[1] === sidePath)) {
    throw new Error("這組雙鏡頭影像已經加入。");
  }
  return [
    ...pairs,
    [topPath, sidePath],
  ];
}

export function parseRigidTransform(matrix) {
  if (
    !Array.isArray(matrix)
    || matrix.length !== 4
    || matrix.some((row) => !Array.isArray(row) || row.length !== 4)
  ) {
    throw new Error("T_world_from_stereo 必須是 4 × 4 矩陣。");
  }
  const parsed = matrix.map((row) => row.map((value) => finiteNumber(
    value,
    "T_world_from_stereo",
  )));
  const rotation = parsed.slice(0, 3).map((row) => row.slice(0, 3));
  const columns = [0, 1, 2].map((column) => rotation.map((row) => row[column]));

  for (let index = 0; index < 3; index += 1) {
    if (!near(dot(columns[index], columns[index]), 1)) {
      throw new Error("T_world_from_stereo 的旋轉部分必須是正交矩陣。");
    }
    for (let second = index + 1; second < 3; second += 1) {
      if (!near(dot(columns[index], columns[second]), 0)) {
        throw new Error("T_world_from_stereo 的旋轉部分必須是正交矩陣。");
      }
    }
  }
  if (!near(determinant3(rotation), 1)) {
    throw new Error("T_world_from_stereo 的旋轉矩陣行列式必須為 1。");
  }
  if (
    !near(parsed[3][0], 0)
    || !near(parsed[3][1], 0)
    || !near(parsed[3][2], 0)
    || !near(parsed[3][3], 1)
  ) {
    throw new Error("T_world_from_stereo 最後一列必須為 0、0、0、1。");
  }
  return parsed;
}

export function buildCalibrationCreatePayload(draft) {
  if (!draft.topImagePaths.length) {
    throw new Error("請至少選擇一張俯視角單鏡頭校正影像。");
  }
  if (!draft.sideImagePaths.length) {
    throw new Error("請至少選擇一張側視角單鏡頭校正影像。");
  }
  if (!draft.stereoImagePairs.length) {
    throw new Error("請至少建立一組雙鏡頭校正影像配對。");
  }
  const sidePaths = new Set(draft.sideImagePaths);
  if (draft.topImagePaths.some((path) => sidePaths.has(path))) {
    throw new Error("同一張影像不可同時作為俯視角與側視角單鏡頭校正來源。");
  }
  if (draft.rotatingImages.length > 0) {
    if (draft.rotatingImages.length < 3) {
      throw new Error("環繞校正至少需要三張不同角度的影像。");
    }
    const angles = draft.rotatingImages.map((item) => finiteNumber(
      item.angleDeg,
      "環繞校正角度",
    ));
    if (new Set(angles).size < 3) {
      throw new Error("環繞校正至少需要三個不同的馬達角度。");
    }
  }
  if (!draft.worldTransformConfirmed) {
    throw new Error("請確認 T_world_from_stereo 已經實際量測或驗證。");
  }
  const worldLabels = [
    draft.worldOrigin,
    draft.worldXAxis,
    draft.worldYAxis,
    draft.worldZAxis,
  ];
  if (worldLabels.some((value) => !String(value || "").trim())) {
    throw new Error("世界座標原點與 X、Y、Z 軸方向都必須明確填寫。");
  }

  return {
    top_camera_identifier: "top",
    side_camera_identifier: "side",
    rotating_camera_identifier: "rotating",
    top_image_paths: [...draft.topImagePaths],
    side_image_paths: [...draft.sideImagePaths],
    stereo_image_pairs: draft.stereoImagePairs.map((pair) => [...pair]),
    rotating_images: draft.rotatingImages.map((item) => ({
      path: item.path,
      angle_deg: finiteNumber(item.angleDeg, "環繞校正角度"),
    })),
    camera_model_name: "CM1.3M30M12Q",
    sensor_name: "AR0130",
    sensor_width_mm: 4.83,
    sensor_height_mm: 3.63,
    focal_length_mm: 2.1,
    diagonal_fov_deg: 126,
    pattern_columns: integerAtLeastTwo(
      draft.patternColumns,
      "單鏡頭棋盤內角點欄數",
    ),
    pattern_rows: integerAtLeastTwo(
      draft.patternRows,
      "單鏡頭棋盤內角點列數",
    ),
    square_size_mm_x: positiveNumber(
      draft.squareSizeMmX,
      "單鏡頭棋盤格 X 尺寸",
    ),
    square_size_mm_y: positiveNumber(
      draft.squareSizeMmY,
      "單鏡頭棋盤格 Y 尺寸",
    ),
    stereo_pattern_columns: integerAtLeastTwo(
      draft.stereoPatternColumns,
      "雙鏡頭棋盤內角點欄數",
    ),
    stereo_pattern_rows: integerAtLeastTwo(
      draft.stereoPatternRows,
      "雙鏡頭棋盤內角點列數",
    ),
    stereo_square_size_mm_x: positiveNumber(
      draft.stereoSquareSizeMmX,
      "雙鏡頭棋盤格 X 尺寸",
    ),
    stereo_square_size_mm_y: positiveNumber(
      draft.stereoSquareSizeMmY,
      "雙鏡頭棋盤格 Y 尺寸",
    ),
    individual_board_width_cm: positiveNumber(
      draft.individualBoardWidthCm,
      "單鏡頭校正板寬度",
    ),
    individual_board_height_cm: positiveNumber(
      draft.individualBoardHeightCm,
      "單鏡頭校正板高度",
    ),
    stereo_board_width_cm: positiveNumber(
      draft.stereoBoardWidthCm,
      "雙鏡頭校正板寬度",
    ),
    stereo_board_height_cm: positiveNumber(
      draft.stereoBoardHeightCm,
      "雙鏡頭校正板高度",
    ),
    notes: String(draft.notes || "").trim(),
    world_coordinate_system: {
      origin: draft.worldOrigin.trim(),
      x_axis: draft.worldXAxis.trim(),
      y_axis: draft.worldYAxis.trim(),
      z_axis: draft.worldZAxis.trim(),
      unit: "mm",
    },
    world_transform_matrix: parseRigidTransform(draft.worldTransformMatrix),
  };
}

export function calibrationBaselineComparison(draft) {
  const individualComplete = [
    draft.individualBoardWidthCm,
    draft.individualBoardHeightCm,
  ].every((value) => String(value ?? "").trim());
  const stereoComplete = [
    draft.stereoBoardWidthCm,
    draft.stereoBoardHeightCm,
  ].every((value) => String(value ?? "").trim());
  const patternComplete = [
    draft.patternColumns,
    draft.patternRows,
  ].every((value) => String(value ?? "").trim());
  const individual = [
    Number(draft.individualBoardWidthCm),
    Number(draft.individualBoardHeightCm),
  ];
  const stereo = [
    Number(draft.stereoBoardWidthCm),
    Number(draft.stereoBoardHeightCm),
  ];
  const pattern = [
    Number(draft.patternColumns),
    Number(draft.patternRows),
  ];
  return {
    individualComplete,
    stereoComplete,
    patternComplete,
    individualMatches: individualComplete && individual.every(
      (value, index) => value === CALIBRATION_PAPER_BASELINE.individualBoardSizeCm[index],
    ),
    stereoMatches: stereoComplete && stereo.every(
      (value, index) => value === CALIBRATION_PAPER_BASELINE.stereoBoardSizeCm[index],
    ),
    patternMatches: patternComplete && pattern.every(
      (value, index) => value === CALIBRATION_PAPER_BASELINE.individualPattern[index],
    ),
  };
}

export function calibrationPreviewItems(profile) {
  const items = [];
  for (const cameraId of ["top", "side", "rotating"]) {
    for (const detection of profile?.corner_detections?.[cameraId] || []) {
      if (detection?.preview_name) {
        items.push({
          cameraId,
          found: Boolean(detection.found),
          imageId: detection.image_id,
          previewName: detection.preview_name,
        });
      }
    }
  }
  for (const pair of profile?.corner_detections?.stereo || []) {
    for (const cameraId of ["top", "side"]) {
      const detection = pair?.[cameraId];
      if (detection?.preview_name) {
        items.push({
          cameraId: `stereo:${cameraId}`,
          found: Boolean(detection.found),
          imageId: detection.image_id,
          pairId: pair.pair_id,
          previewName: detection.preview_name,
        });
      }
    }
  }
  return items;
}

export function calibrationWorkflowAvailability(profile) {
  const topCorners = (profile?.corner_detections?.top || []).some(
    (item) => item.found,
  );
  const sideCorners = (profile?.corner_detections?.side || []).some(
    (item) => item.found,
  );
  const stereoCorners = (profile?.corner_detections?.stereo || []).some(
    (item) => item.usable,
  );
  const rotatingSelected = Boolean(profile?.selected_images?.rotating?.length);
  const rotatingCorners = (profile?.corner_detections?.rotating || []).filter(
    (item) => item.found,
  );
  const intrinsicsReady = Boolean(
    profile?.top_camera_matrix
    && profile?.top_distortion_coefficients
    && profile?.side_camera_matrix
    && profile?.side_distortion_coefficients,
  );
  const stereoReady = Boolean(
    profile?.rotation_matrix
    && profile?.translation_vector
    && profile?.essential_matrix
    && profile?.fundamental_matrix
    && profile?.top_projection_matrix
    && profile?.side_projection_matrix
    && profile?.disparity_to_depth_matrix,
  );
  const rotatingIntrinsicsReady = Boolean(
    profile?.rotating_camera_matrix
    && profile?.rotating_distortion_coefficients,
  );
  const rotatingReady = !rotatingSelected || Boolean(
    profile?.rotating_axis_origin_mm
    && profile?.rotating_axis_direction
    && profile?.rotating_axis_from_camera_matrix,
  );
  return {
    corners: true,
    intrinsics: topCorners && sideCorners,
    stereo: intrinsicsReady && stereoCorners,
    rotating: rotatingSelected
      && rotatingIntrinsicsReady
      && stereoReady
      && new Set(rotatingCorners.map((item) => item.angle_deg)).size >= 3,
    validate: intrinsicsReady && stereoReady && rotatingReady,
  };
}

export function calibrationWorkflowStepState(
  profile,
  key,
) {
  if (key === "corners") {
    const topReady = (profile?.corner_detections?.top || []).some(
      (item) => item.found,
    );
    const sideReady = (profile?.corner_detections?.side || []).some(
      (item) => item.found,
    );
    const stereoReady = (profile?.corner_detections?.stereo || []).some(
      (item) => item.usable,
    );
    return topReady && sideReady && stereoReady
      ? "已完成"
      : "尚未執行";
  }
  if (key === "intrinsics") {
    return profile?.top_camera_matrix && profile?.side_camera_matrix
      ? "已完成"
      : "尚未執行";
  }
  if (key === "stereo") {
    const available = calibrationWorkflowAvailability(profile);
    return available.validate
      ? "已完成"
      : "尚未執行";
  }
  if (key === "rotating") {
    if (!profile?.selected_images?.rotating?.length) return "不需要";
    return profile?.rotating_axis_from_camera_matrix
      ? "已完成"
      : "尚未執行";
  }
  return profile?.valid
    ? "已通過"
    : profile?.status === "potentially_invalid"
      ? "可能失效"
      : "尚未通過";
}

export function formatCalibrationNumber(
  value,
  maximumFractionDigits = 6,
) {
  const parsed = Number(value);
  return Number.isFinite(parsed)
    ? parsed.toLocaleString("zh-TW", {
      maximumFractionDigits,
    })
    : "—";
}

export function formatCalibrationPercent(value) {
  const parsed = Number(value);
  return Number.isFinite(parsed)
    ? `${(parsed * 100).toFixed(1)}%`
    : "—";
}

export function distortionNamed(coefficients) {
  const names = ["k1", "k2", "p1", "p2", "k3"];
  return names.map((name, index) => ({
    name,
    value: Array.isArray(coefficients) ? coefficients[index] : null,
  }));
}

export function calibrationDateTime(value) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString("zh-TW", {
    hour12: false,
  });
}

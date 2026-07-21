"use client";

import { FiSave } from "react-icons/fi";

import Button from "@/components/buttons/Button";
import RetryMessage from "@/components/feedback/RetryMessage";
import {
  NumericInput,
  SelectInput,
} from "@/components/inputs/Input";
import { ToggleRow } from "@/components/inputs/Toggle";
import InnerPanel from "@/components/panels/InnerPanel";
import SettingPanel from "@/components/panels/SettingPanel";
import SubsectionHeader from "@/components/headers/SubsectionHeader";
import useSettings from "@/hooks/useSettings";
import { cloneValue } from "@/features/Settings/lib/settingsUtils";

const MARKERS = [
  ["left_rear", "左後", "left_rear_id"],
  ["right_rear", "右後", "right_rear_id"],
  ["left_front", "左前", "left_front_id"],
  ["right_front", "右前", "right_front_id"],
];

const DICTIONARY_OPTIONS = [
  "DICT_4X4_50",
  "DICT_5X5_100",
  "DICT_6X6_250",
  "DICT_7X7_250",
];

const DICTIONARY_CAPACITY = {
  DICT_4X4_50: 50,
  DICT_5X5_100: 100,
  DICT_6X6_250: 250,
  DICT_7X7_250: 250,
};

const ORIGIN_OPTIONS = [
  { value: "layout_center", label: "配置中心" },
  { value: "left_rear", label: "左後 Marker 中心" },
  { value: "right_rear", label: "右後 Marker 中心" },
  { value: "left_front", label: "左前 Marker 中心" },
  { value: "right_front", label: "右前 Marker 中心" },
];

function requiredNumber(
  value,
  label,
  {
    minimum,
    integer = false,
  } = {},
) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed) || (integer && !Number.isInteger(parsed))) {
    throw new Error(`${label}必須是有效${integer ? "整數" : "數值"}。`);
  }
  if (minimum !== undefined && parsed < minimum) {
    throw new Error(`${label}不可小於 ${minimum}。`);
  }
  return parsed;
}

function optionalNumber(
  value,
  label,
  minimum,
) {
  if (String(value ?? "").trim() === "") return null;
  return requiredNumber(value, label, { minimum });
}

function defaultMarkerCenters(world) {
  const halfWidth = Number(world.left_right_center_distance_mm || 0) / 2;
  const halfDepth = Number(world.rear_front_center_distance_mm || 0) / 2;
  const xSign = world.x_axis_direction === "left" ? -1 : 1;
  const ySign = world.y_axis_direction === "rear" ? -1 : 1;
  const centers = {
    left_rear: {
      x_mm: -halfWidth * xSign,
      y_mm: -halfDepth * ySign,
      z_mm: 0,
      orientation_deg: Number(world.marker_orientation_deg || 0),
    },
    right_rear: {
      x_mm: halfWidth * xSign,
      y_mm: -halfDepth * ySign,
      z_mm: 0,
      orientation_deg: Number(world.marker_orientation_deg || 0),
    },
    left_front: {
      x_mm: -halfWidth * xSign,
      y_mm: halfDepth * ySign,
      z_mm: 0,
      orientation_deg: Number(world.marker_orientation_deg || 0),
    },
    right_front: {
      x_mm: halfWidth * xSign,
      y_mm: halfDepth * ySign,
      z_mm: 0,
      orientation_deg: Number(world.marker_orientation_deg || 0),
    },
  };
  if (world.world_origin === "layout_center") return centers;

  const offset = centers[world.world_origin];
  return Object.fromEntries(
    Object.entries(centers).map(([position, center]) => ([
      position,
      {
        ...center,
        x_mm: center.x_mm - offset.x_mm,
        y_mm: center.y_mm - offset.y_mm,
      },
    ])),
  );
}

function markerCentersForOrigin(
  centers,
  origin,
) {
  const values = MARKERS.map(([position]) => centers[position]);
  if (values.some((center) => !center)) return centers;

  const offset = origin === "layout_center"
    ? {
        x_mm: values.reduce((sum, center) => sum + Number(center.x_mm), 0) / values.length,
        y_mm: values.reduce((sum, center) => sum + Number(center.y_mm), 0) / values.length,
        z_mm: values.reduce((sum, center) => sum + Number(center.z_mm), 0) / values.length,
      }
    : centers[origin];

  return Object.fromEntries(
    MARKERS.map(([position]) => {
      const center = centers[position];
      return [
        position,
        {
          ...center,
          x_mm: Number(center.x_mm) - Number(offset.x_mm),
          y_mm: Number(center.y_mm) - Number(offset.y_mm),
          z_mm: Number(center.z_mm) - Number(offset.z_mm),
        },
      ];
    }),
  );
}

function serializePoseAlignment(payload) {
  const next = cloneValue(payload);
  const settings = next.pose_alignment;
  const world = settings.aruco_world;
  const markerIds = MARKERS.map(([, label, key]) => (
    requiredNumber(world[key], `${label} Marker ID`, {
      minimum: 0,
      integer: true,
    })
  ));

  if (new Set(markerIds).size !== MARKERS.length) {
    throw new Error("四個 ArUco Marker ID 不可重複。");
  }
  const dictionaryCapacity = DICTIONARY_CAPACITY[world.dictionary];
  if (
    dictionaryCapacity
    && markerIds.some((markerId) => markerId >= dictionaryCapacity)
  ) {
    throw new Error(
      `${world.dictionary} 的 Marker ID 必須小於 ${dictionaryCapacity}。`,
    );
  }
  MARKERS.forEach(([, , key], index) => {
    world[key] = markerIds[index];
  });
  world.marker_size_mm = requiredNumber(
    world.marker_size_mm,
    "Marker 邊長",
    { minimum: 0.001 },
  );
  world.left_right_center_distance_mm = requiredNumber(
    world.left_right_center_distance_mm,
    "左右中心距離",
    { minimum: 0.001 },
  );
  world.rear_front_center_distance_mm = requiredNumber(
    world.rear_front_center_distance_mm,
    "前後中心距離",
    { minimum: 0.001 },
  );
  world.marker_orientation_deg = requiredNumber(
    world.marker_orientation_deg,
    "Marker 朝向",
  );

  if (world.advanced_mode) {
    const centers = world.marker_centers_world_mm || {};
    for (const [position, label] of MARKERS) {
      const center = centers[position];
      if (!center) throw new Error(`請填寫${label} Marker 世界座標。`);
      for (const axis of ["x", "y", "z"]) {
        center[`${axis}_mm`] = requiredNumber(
          center[`${axis}_mm`],
          `${label} ${axis.toUpperCase()} 座標`,
        );
      }
      center.orientation_deg = requiredNumber(
        center.orientation_deg,
        `${label} Marker 朝向`,
      );
    }
  } else {
    world.marker_centers_world_mm = {};
  }

  const priors = settings.camera_priors;
  for (const [cameraId, label] of [
    ["top", "俯視相機"],
    ["side", "側視相機"],
  ]) {
    priors[cameraId].height_mm = optionalNumber(
      priors[cameraId].height_mm,
      `${label}高度`,
      0,
    );
    priors[cameraId].horizontal_distance_to_center_mm = optionalNumber(
      priors[cameraId].horizontal_distance_to_center_mm,
      `${label}至平台中心水平距離`,
      0,
    );
    priors[cameraId].facing_center_angle_deg = optionalNumber(
      priors[cameraId].facing_center_angle_deg,
      `${label}面向中心預估角度`,
    );
  }
  priors.rotating.arm_height_mm = optionalNumber(
    priors.rotating.arm_height_mm,
    "旋臂高度",
    0,
  );
  settings.minimum_pnp_inliers = requiredNumber(
    settings.minimum_pnp_inliers,
    "PnP 最少內點",
    { minimum: 4, integer: true },
  );
  settings.maximum_aruco_reprojection_error_px = requiredNumber(
    settings.maximum_aruco_reprojection_error_px,
    "ArUco 最大重投影誤差",
    { minimum: 0.001 },
  );
  settings.minimum_sfm_matches = requiredNumber(
    settings.minimum_sfm_matches,
    "SfM 最少特徵配對",
    { minimum: 8, integer: true },
  );
  return next;
}

function diagramCenters(world) {
  if (world.advanced_mode) {
    const centers = world.marker_centers_world_mm || {};
    if (MARKERS.every(([position]) => centers[position])) return centers;
  }
  return defaultMarkerCenters(world);
}

function ArucoTopView({ world }) {
  const centers = diagramCenters(world);
  const points = MARKERS.map(([position, label, idKey]) => ({
    position,
    label,
    id: world[idKey],
    x: Number(centers[position]?.x_mm || 0),
    y: Number(centers[position]?.y_mm || 0),
  }));
  const xs = [0, ...points.map((point) => point.x)];
  const ys = [0, ...points.map((point) => point.y)];
  const minimumX = Math.min(...xs);
  const maximumX = Math.max(...xs);
  const minimumY = Math.min(...ys);
  const maximumY = Math.max(...ys);
  const width = Math.max(1, maximumX - minimumX);
  const height = Math.max(1, maximumY - minimumY);
  const originLeft = 10 + ((0 - minimumX) / width) * 80;
  const originTop = 10 + ((0 - minimumY) / height) * 80;
  const selectedOriginLabel = ORIGIN_OPTIONS.find((option) => (
    option.value === world.world_origin
  ))?.label;
  const originLabel = world.advanced_mode
    ? `${selectedOriginLabel} (0, 0, 0)`
    : selectedOriginLabel;

  return (
    <InnerPanel className="relative min-h-80 overflow-hidden bg-emerald-950/20">
      <div className="absolute inset-8 rounded-xl border border-dashed border-emerald-200/30">
        <span
          className="absolute z-10 size-3 -translate-x-1/2 -translate-y-1/2 rounded-full border border-emerald-100 bg-emerald-300"
          style={{
            left: `${originLeft}%`,
            top: `${originTop}%`,
          }}
        />
        <span
          className="absolute z-10 translate-x-2 translate-y-2 whitespace-nowrap text-xs font-black text-emerald-200"
          style={{
            left: `${originLeft}%`,
            top: `${originTop}%`,
          }}
        >
          世界原點：{originLabel}
        </span>
        {points.map((point) => (
          <div
            key={point.position}
            className="absolute grid size-20 -translate-x-1/2 -translate-y-1/2 place-items-center rounded-xl border border-emerald-200/50 bg-black/50 text-center shadow-lg"
            style={{
              left: `${10 + ((point.x - minimumX) / width) * 80}%`,
              top: `${10 + ((point.y - minimumY) / height) * 80}%`,
            }}
          >
            <span className="text-xs font-black text-emerald-200">
              {point.label} ID {point.id}
            </span>
          </div>
        ))}
        <span className="absolute right-2 bottom-2 text-xs font-bold text-neutral-300">
          Marker 邊長 {world.marker_size_mm} mm
        </span>
        <span className="absolute top-2 left-1/2 -translate-x-1/2 text-xs font-bold text-neutral-300">
          左右中心距離 {world.left_right_center_distance_mm} mm
        </span>
        <span className="absolute top-1/2 left-2 -translate-y-1/2 [writing-mode:vertical-rl] text-xs font-bold text-neutral-300">
          前後中心距離 {world.rear_front_center_distance_mm} mm
        </span>
        <span className="absolute bottom-2 left-2 text-xs font-bold text-neutral-300">
          X {world.x_axis_direction === "right" ? "向右" : "向左"}
          {" · "}
          Y {world.y_axis_direction === "front" ? "向前" : "向後"}
          {" · "}
          Z {world.z_axis_direction === "up" ? "向上" : "向下"}
        </span>
      </div>
    </InnerPanel>
  );
}

function update(
  updateField,
  path,
) {
  return (value) => updateField(path, value);
}

export default function ArucoWorldSettings({
  open,
  onNotify,
}) {
  const {
    payload,
    loading,
    saving,
    loadFailed,
    loadError,
    loadGroup,
    updateField,
    saveGroup,
  } = useSettings({
    group: "pose_alignment",
    onNotify,
    open,
    serializePayload: serializePoseAlignment,
  });
  const settings = payload?.pose_alignment;
  const world = settings?.aruco_world;

  function setAdvancedMode(enabled) {
    updateField(
      ["pose_alignment", "aruco_world", "advanced_mode"],
      enabled,
    );
    if (enabled && Object.keys(world.marker_centers_world_mm || {}).length !== 4) {
      updateField(
        ["pose_alignment", "aruco_world", "marker_centers_world_mm"],
        defaultMarkerCenters(world),
      );
    }
  }

  function setWorldOrigin(origin) {
    if (world.advanced_mode) {
      updateField(
        ["pose_alignment", "aruco_world", "marker_centers_world_mm"],
        markerCentersForOrigin(
          world.marker_centers_world_mm,
          origin,
        ),
      );
    }
    updateField(
      ["pose_alignment", "aruco_world", "world_origin"],
      origin,
    );
  }

  return (
    <SettingPanel
      label="ArUco 世界基準"
      open={open}
      locked={saving}
      footer={(
        <Button
          variant="primary"
          disabled={!payload || loading || saving}
          onClick={() => void saveGroup()}
        >
          <FiSave
            className="size-4 shrink-0"
            aria-hidden="true"
          />
          {saving ? "儲存中…" : "儲存 ArUco 世界基準"}
        </Button>
      )}
    >
      {loading && !payload ? (
        <p className="grid min-h-28 place-items-center text-sm font-semibold text-neutral-400">
          讀取 ArUco 世界基準中…
        </p>
      ) : null}
      {!loading && !payload && loadFailed ? (
        <RetryMessage
          message={loadError || "讀取 ArUco 世界基準失敗。"}
          onRetry={() => void loadGroup()}
          retrying={loading}
        />
      ) : null}
      {world ? (
        <div className="grid gap-5">
          <SubsectionHeader
            title="ArUco 世界基準"
            description="四個 Marker 共同定義毫米世界座標；所有距離皆為 Marker 中心至中心。"
          />
          <ArucoTopView world={world} />

          <InnerPanel>
            <div className="grid gap-3 min-[720px]:grid-cols-2 min-[1180px]:grid-cols-4">
              <SelectInput
                id="aruco-dictionary"
                label="ArUco Dictionary"
                value={world.dictionary}
                options={DICTIONARY_OPTIONS}
                onValueChange={update(
                  updateField,
                  ["pose_alignment", "aruco_world", "dictionary"],
                )}
              />
              {MARKERS.map(([, label, key]) => (
                <NumericInput
                  key={key}
                  id={`aruco-${key}`}
                  label={`${label} ID`}
                  value={world[key]}
                  min={0}
                  step={1}
                  onValueChange={update(
                    updateField,
                    ["pose_alignment", "aruco_world", key],
                  )}
                />
              ))}
              <NumericInput
                id="aruco-marker-size"
                label="Marker 邊長"
                value={world.marker_size_mm}
                min={0.001}
                step={0.1}
                suffix="mm"
                onValueChange={update(
                  updateField,
                  ["pose_alignment", "aruco_world", "marker_size_mm"],
                )}
              />
              <NumericInput
                id="aruco-horizontal-distance"
                label="左右中心距離"
                value={world.left_right_center_distance_mm}
                min={0.001}
                step={0.1}
                suffix="mm"
                onValueChange={update(
                  updateField,
                  ["pose_alignment", "aruco_world", "left_right_center_distance_mm"],
                )}
              />
              <NumericInput
                id="aruco-depth-distance"
                label="前後中心距離"
                value={world.rear_front_center_distance_mm}
                min={0.001}
                step={0.1}
                suffix="mm"
                onValueChange={update(
                  updateField,
                  ["pose_alignment", "aruco_world", "rear_front_center_distance_mm"],
                )}
              />
              <NumericInput
                id="aruco-marker-orientation"
                label="Marker 朝向"
                value={world.marker_orientation_deg}
                min={-360}
                max={360}
                step={0.1}
                suffix="度"
                description="0° 表示 Marker 上緣朝世界 Y 軸負方向。"
                onValueChange={update(
                  updateField,
                  ["pose_alignment", "aruco_world", "marker_orientation_deg"],
                )}
              />
              <SelectInput
                id="aruco-world-origin"
                label="世界原點"
                value={world.world_origin}
                options={ORIGIN_OPTIONS}
                onValueChange={setWorldOrigin}
              />
              <SelectInput
                id="aruco-x-axis"
                label="X 軸方向"
                value={world.x_axis_direction}
                options={[
                  { value: "right", label: "向右" },
                  { value: "left", label: "向左" },
                ]}
                onValueChange={update(
                  updateField,
                  ["pose_alignment", "aruco_world", "x_axis_direction"],
                )}
              />
              <SelectInput
                id="aruco-y-axis"
                label="Y 軸方向"
                value={world.y_axis_direction}
                options={[
                  { value: "front", label: "向前" },
                  { value: "rear", label: "向後" },
                ]}
                onValueChange={update(
                  updateField,
                  ["pose_alignment", "aruco_world", "y_axis_direction"],
                )}
              />
              <SelectInput
                id="aruco-z-axis"
                label="Z 軸方向"
                value={world.z_axis_direction}
                options={[
                  { value: "up", label: "向上" },
                  { value: "down", label: "向下" },
                ]}
                onValueChange={update(
                  updateField,
                  ["pose_alignment", "aruco_world", "z_axis_direction"],
                )}
              />
            </div>
          </InnerPanel>

          <ToggleRow
            checked={world.advanced_mode}
            label="進階世界座標"
            description="開啟後直接指定每個 Marker 中心的毫米世界座標與朝向。"
            onClick={() => setAdvancedMode(!world.advanced_mode)}
          />

          {world.advanced_mode ? (
            <div className="grid gap-3 min-[900px]:grid-cols-2">
              {MARKERS.map(([position, label]) => {
                const center = world.marker_centers_world_mm[position];
                return (
                  <InnerPanel key={position}>
                    <h4 className="m-0 text-sm font-black text-emerald-200">
                      {label} Marker 中心
                    </h4>
                    <div className="grid grid-cols-2 gap-3">
                      {["x", "y", "z"].map((axis) => (
                        <NumericInput
                          key={axis}
                          id={`aruco-${position}-${axis}`}
                          label={`${axis.toUpperCase()} 座標`}
                          value={center?.[`${axis}_mm`] ?? ""}
                          step={0.1}
                          suffix="mm"
                          onValueChange={update(
                            updateField,
                            [
                              "pose_alignment",
                              "aruco_world",
                              "marker_centers_world_mm",
                              position,
                              `${axis}_mm`,
                            ],
                          )}
                        />
                      ))}
                      <NumericInput
                        id={`aruco-${position}-orientation`}
                        label="Marker 朝向"
                        value={center?.orientation_deg ?? ""}
                        min={-360}
                        max={360}
                        step={0.1}
                        suffix="度"
                        onValueChange={update(
                          updateField,
                          [
                            "pose_alignment",
                            "aruco_world",
                            "marker_centers_world_mm",
                            position,
                            "orientation_deg",
                          ],
                        )}
                      />
                    </div>
                  </InnerPanel>
                );
              })}
            </div>
          ) : null}

          <SubsectionHeader
            title="相機安裝先驗"
            description="僅供姿態初始值、合理性檢查與短暫遮擋輔助，不會作為正式外參。"
          />
          <div className="grid gap-3 min-[900px]:grid-cols-3">
            {["top", "side"].map((cameraId) => {
              const label = cameraId === "top" ? "俯視相機" : "側視相機";
              const prior = settings.camera_priors[cameraId];
              return (
                <InnerPanel key={cameraId}>
                  <h4 className="m-0 text-sm font-black text-emerald-200">
                    {label}
                  </h4>
                  <NumericInput
                    id={`${cameraId}-prior-height`}
                    label="高度"
                    value={prior.height_mm ?? ""}
                    min={0}
                    step={0.1}
                    suffix="mm"
                    onValueChange={update(
                      updateField,
                      ["pose_alignment", "camera_priors", cameraId, "height_mm"],
                    )}
                  />
                  <NumericInput
                    id={`${cameraId}-prior-distance`}
                    label="至平台中心水平距離"
                    value={prior.horizontal_distance_to_center_mm ?? ""}
                    min={0}
                    step={0.1}
                    suffix="mm"
                    onValueChange={update(
                      updateField,
                      [
                        "pose_alignment",
                        "camera_priors",
                        cameraId,
                        "horizontal_distance_to_center_mm",
                      ],
                    )}
                  />
                  <NumericInput
                    id={`${cameraId}-prior-angle`}
                    label="面向中心預估角度"
                    value={prior.facing_center_angle_deg ?? ""}
                    min={-360}
                    max={360}
                    step={0.1}
                    suffix="度"
                    onValueChange={update(
                      updateField,
                      [
                        "pose_alignment",
                        "camera_priors",
                        cameraId,
                        "facing_center_angle_deg",
                      ],
                    )}
                  />
                </InnerPanel>
              );
            })}
            <InnerPanel>
              <h4 className="m-0 text-sm font-black text-emerald-200">
                旋臂相機
              </h4>
              <NumericInput
                id="rotating-prior-height"
                label="旋臂高度"
                value={settings.camera_priors.rotating.arm_height_mm ?? ""}
                min={0}
                step={0.1}
                suffix="mm"
                description="馬達角度會自動取自 Capture Record。"
                onValueChange={update(
                  updateField,
                  ["pose_alignment", "camera_priors", "rotating", "arm_height_mm"],
                )}
              />
            </InnerPanel>
          </div>
        </div>
      ) : null}
    </SettingPanel>
  );
}

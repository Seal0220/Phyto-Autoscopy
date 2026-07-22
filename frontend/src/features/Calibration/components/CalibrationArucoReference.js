"use client";

import { FiSave } from "react-icons/fi";

import ActionRow from "@/components/actions/ActionRow";
import Button from "@/components/buttons/Button";
import RetryMessage from "@/components/feedback/RetryMessage";
import {
  NumericInput,
  SelectInput,
} from "@/components/inputs/Input";
import InnerPanel from "@/components/panels/InnerPanel";
import useSettings from "@/hooks/useSettings";
import { cloneValue } from "@/features/Settings/lib/settingsUtils";

const MARKERS = [
  ["left_rear", "左上", "left_rear_id"],
  ["right_rear", "右上", "right_rear_id"],
  ["left_front", "左下", "left_front_id"],
  ["right_front", "右下", "right_front_id"],
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

function serializePoseAlignment(payload) {
  const next = cloneValue(payload);
  const settings = next.pose_alignment;
  const world = settings.aruco_world;
  const markerIds = MARKERS.map(([, label, key]) => (
    requiredNumber(world[key], `${label} 標籤ID`, {
      minimum: 0,
      integer: true,
    })
  ));

  if (new Set(markerIds).size !== MARKERS.length) {
    throw new Error("四個 ArUco 標籤ID 不可重複。");
  }
  const dictionaryCapacity = DICTIONARY_CAPACITY[world.dictionary];
  if (
    dictionaryCapacity
    && markerIds.some((markerId) => markerId >= dictionaryCapacity)
  ) {
    throw new Error(
      `${world.dictionary} 的 標籤ID 必須小於 ${dictionaryCapacity}。`,
    );
  }
  MARKERS.forEach(([, , key], index) => {
    world[key] = markerIds[index];
  });
  world.marker_size_mm = requiredNumber(
    world.marker_size_mm,
    "標籤邊長",
    { minimum: 0.001 },
  );
  world.left_right_center_distance_mm = requiredNumber(
    world.left_right_center_distance_mm,
    "左右中心距離",
    { minimum: 0.001 },
  );
  world.rear_front_center_distance_mm = requiredNumber(
    world.rear_front_center_distance_mm,
    "上下中心距離",
    { minimum: 0.001 },
  );
  world.marker_orientation_deg = requiredNumber(
    world.marker_orientation_deg,
    "標籤朝向",
  );

  if (world.advanced_mode) {
    const centers = world.marker_centers_world_mm || {};
    for (const [position, label] of MARKERS) {
      const center = centers[position];
      if (!center) throw new Error(`請填寫${label} 標籤世界座標。`);
      for (const axis of ["x", "y", "z"]) {
        center[`${axis}_mm`] = requiredNumber(
          center[`${axis}_mm`],
          `${label} ${axis.toUpperCase()} 座標`,
        );
      }
      center.orientation_deg = requiredNumber(
        center.orientation_deg,
        `${label} 標籤朝向`,
      );
    }
  } else {
    world.marker_centers_world_mm = {};
  }

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
  return (
    <InnerPanel className="place-self-center mx-auto relative size-120 overflow-hidden bg-emerald-950/20">
      <div className="absolute inset-14 rounded-xl border border-dashed border-emerald-200/30">
        <span
          className="absolute z-10 size-3 -translate-x-1/2 -translate-y-1/2 rounded-full border border-emerald-100 bg-emerald-300"
          style={{
            left: `${originLeft}%`,
            top: `${originTop}%`,
          }}
        />
        <div
          className="absolute z-10 translate-x-2 translate-y-2 whitespace-nowrap flex flex-col gap-0.5"
          style={{
            left: `${originLeft}%`,
            top: `${originTop}%`,
          }}
        >
          <span className="text-sm font-black text-emerald-200">原點</span>
          <span className="text-xs font-bold text-neutral-300">
            X {world.x_axis_direction === "right" ? "向右" : "向左"}
            {" · "}
            Y {world.y_axis_direction === "front" ? "向下" : "向上"}
            {" · "}
            Z {world.z_axis_direction === "up" ? "向上" : "向下"}
          </span>
        </div>


        {points.map((point) => (
          <div
            key={point.position}
            className="absolute grid size-20 -translate-x-1/2 -translate-y-1/2 place-items-center rounded-xl border border-emerald-200/50 bg-black/50 text-center shadow-lg"
            style={{
              left: `${((point.x - minimumX) / width) * 100}%`,
              top: `${((point.y - minimumY) / height) * 100}%`,
            }}
          >
            <span className="text-xs font-black text-emerald-200">
              [{point.id}] {point.label}
            </span>
          </div>
        ))}
        <span className="absolute left-12 bottom-2 text-xs font-bold text-neutral-300 flex gap-1 justify-center items-center">
          <span>標籤邊長</span>
          <span className="text-sm font-black text-emerald-200">{world.marker_size_mm} mm</span>
        </span>
        <span className="absolute top-2 left-1/2 -translate-x-1/2 text-xs font-bold text-neutral-300 flex gap-2 justify-center items-center">
          <span>左右中心距離</span>
          <span className="text-sm font-black text-emerald-200">{world.left_right_center_distance_mm} mm</span>
        </span>
        <span className="absolute top-1/2 left-2 -translate-y-1/2 [writing-mode:vertical-rl] text-xs font-bold text-neutral-300 flex gap-2 justify-center items-center">
          <span>上下中心距離</span>
          <span className="text-sm font-black text-emerald-200">{world.rear_front_center_distance_mm} mm</span>
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

export default function CalibrationArucoReference({
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
    open: true,
    serializePayload: serializePoseAlignment,
  });
  const settings = payload?.pose_alignment;
  const world = settings?.aruco_world;

  return (
    <div className="grid gap-5 p-5 max-sm:p-4">
      {loading && !payload ? (
        <p className="grid min-h-28 place-items-center text-sm font-semibold text-neutral-400">
          讀取 ArUco 基準中…
        </p>
      ) : null}
      {!loading && !payload && loadFailed ? (
        <RetryMessage
          message={loadError || "讀取 ArUco 基準失敗。"}
          onRetry={() => void loadGroup()}
          retrying={loading}
        />
      ) : null}
      {world ? (
        <div className="grid gap-5">
          <ArucoTopView world={world} />

          <InnerPanel className="w-fit mx-auto place-self-center">
            <div className="flex flex-row gap-3">
              <SelectInput
                id="aruco-dictionary"
                className="w-40"
                label="ArUco 庫"
                value={world.dictionary}
                options={DICTIONARY_OPTIONS}
                onValueChange={update(
                  updateField,
                  ["pose_alignment", "aruco_world", "dictionary"],
                )}
              />
              <NumericInput
                id="aruco-marker-size"
                className="w-40"
                label="標籤邊長"
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
                className="w-40"
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
                className="w-40"
                label="上下中心距離"
                value={world.rear_front_center_distance_mm}
                min={0.001}
                step={0.1}
                suffix="mm"
                onValueChange={update(
                  updateField,
                  ["pose_alignment", "aruco_world", "rear_front_center_distance_mm"],
                )}
              />
            </div>
          </InnerPanel>
        </div>
      ) : null}
      <ActionRow>
        <Button
          variant="primary"
          disabled={!payload || loading || saving}
          onClick={() => void saveGroup()}
        >
          <FiSave
            className="size-4 shrink-0"
            aria-hidden="true"
          />
          {saving ? "儲存中…" : "儲存 ArUco 基準"}
        </Button>
      </ActionRow>
    </div>
  );
}

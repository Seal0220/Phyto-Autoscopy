"use client";

import { useState } from "react";
import {
  FiArrowDown,
  FiArrowLeft,
  FiArrowRight,
  FiArrowUp,
  FiRotateCcw,
} from "react-icons/fi";

import Button from "@/components/buttons/Button";
import InnerPanel from "@/components/panels/InnerPanel";
import SubsectionHeader from "@/components/headers/SubsectionHeader";

import {
  cameraPositionsFromCalibration,
  projectWorldTrajectory,
  trajectoryPolyline,
} from "../lib/trajectoryUtils";

const VIEW_WIDTH = 760;
const VIEW_HEIGHT = 500;

export default function TrajectoryViewer3D({
  calibration,
  trajectory,
}) {
  const [yaw, setYaw] = useState(35);
  const [pitch, setPitch] = useState(25);
  const cameras = cameraPositionsFromCalibration(calibration);
  const markers = [
    {
      id: "origin",
      label: "植物基部／世界原點",
      point: [0, 0, 0],
      color: "#6ee7b7",
    },
    {
      id: "top-camera",
      label: "俯視相機",
      point: cameras.top,
      color: "#fde68a",
    },
    {
      id: "side-camera",
      label: "側視相機",
      point: cameras.side,
      color: "#fda4af",
    },
  ];
  const refinedTrajectory = trajectory.filter((point) => (
    [point.refinedX, point.refinedY, point.refinedZ].every(
      (value) => value !== null,
    )
  )).map((point) => ({
    ...point,
    x: point.refinedX,
    y: point.refinedY,
    z: point.refinedZ,
  }));
  const projected = projectWorldTrajectory(
    [
      ...trajectory,
      ...refinedTrajectory,
    ],
    markers,
    {
      yawDegrees: yaw,
      pitchDegrees: pitch,
      width: VIEW_WIDTH,
      height: VIEW_HEIGHT,
    },
  );
  const baselinePoints = projected.points.slice(0, trajectory.length);
  const refinedPoints = projected.points.slice(trajectory.length);

  return (
    <InnerPanel>
      <SubsectionHeader
        title="三維植物尖端軌跡"
        description="世界座標單位為 mm；相機位置由校正的 R、t 與 T_world_from_stereo 推導。"
      >
        <Button
          className="min-h-9 px-3 text-xs"
          onClick={() => {
            setYaw(35);
            setPitch(25);
          }}
        >
          <FiRotateCcw
            className="size-3.5 shrink-0"
            aria-hidden="true"
          />
          重設視角
        </Button>
      </SubsectionHeader>

      <div className="grid gap-3 min-[980px]:grid-cols-[minmax(0,1fr)_auto]">
        <div className="aspect-[3/2] min-w-0 overflow-hidden rounded-xl border border-white/10 bg-black/30">
          <svg
            className="size-full"
            viewBox={`0 0 ${VIEW_WIDTH} ${VIEW_HEIGHT}`}
            role="img"
            aria-label="植物尖端三維軌跡等角投影"
          >
            <polyline
              points={trajectoryPolyline(baselinePoints)}
              fill="none"
              stroke={refinedPoints.length ? "#a3a3a3" : "#6ee7b7"}
              strokeWidth="2.5"
              strokeOpacity="0.8"
            />
            {refinedPoints.length ? (
              <polyline
                points={trajectoryPolyline(refinedPoints)}
                fill="none"
                stroke="#6ee7b7"
                strokeWidth="3"
                strokeOpacity="0.95"
              />
            ) : null}
            {baselinePoints.map((
              point,
              index,
            ) => {
              const manual = point.topType === "Manual" || point.sideType === "Manual";
              const highError = point.topError > 10 || point.sideError > 10;
              const color = highError
                ? "#fb7185"
                : manual
                  ? "#ffffff"
                  : "#34d399";
              const endpoint = index === 0 || index === baselinePoints.length - 1;
              return (
                <circle
                  key={`world-${point.frameId}`}
                  cx={point.plotX}
                  cy={point.plotY}
                  r={endpoint ? 6 : 3.5}
                  fill={color}
                  stroke={manual && highError ? "#ffffff" : "#052e22"}
                  strokeWidth={manual && highError ? "3" : "1.5"}
                >
                  <title>
                    {`影格 ${point.frameId} · X ${point.x.toFixed(2)} · Y ${point.y.toFixed(2)} · Z ${point.z.toFixed(2)} mm${manual ? " · 人工修正" : ""}${highError ? " · 高重投影誤差" : ""}`}
                  </title>
                </circle>
              );
            })}
            {baselinePoints.length > 0 ? (
              <>
                <text
                  x={baselinePoints[0].plotX + 8}
                  y={baselinePoints[0].plotY - 8}
                  fill="#d4d4d8"
                  fontSize="12"
                  fontWeight="700"
                >
                  起點
                </text>
                <text
                  x={baselinePoints.at(-1).plotX + 8}
                  y={baselinePoints.at(-1).plotY - 8}
                  fill="#d4d4d8"
                  fontSize="12"
                  fontWeight="700"
                >
                  終點
                </text>
              </>
            ) : null}
            {projected.markers.map((marker) => (
              <g key={marker.id}>
                <rect
                  x={marker.plotX - 5}
                  y={marker.plotY - 5}
                  width="10"
                  height="10"
                  fill={marker.color}
                  transform={`rotate(45 ${marker.plotX} ${marker.plotY})`}
                />
                <text
                  x={marker.plotX + 9}
                  y={marker.plotY - 8}
                  fill={marker.color}
                  fontSize="12"
                  fontWeight="700"
                >
                  {marker.label}
                </text>
              </g>
            ))}
          </svg>
        </div>

        <div className="grid content-start grid-cols-3 gap-2">
          <span />
          <Button
            className="min-h-9 px-3 text-xs"
            aria-label="提高三維視角"
            onClick={() => setPitch((value) => Math.min(80, value + 10))}
          >
            <FiArrowUp
              className="size-3.5 shrink-0"
              aria-hidden="true"
            />
            上
          </Button>
          <span />
          <Button
            className="min-h-9 px-3 text-xs"
            aria-label="向左旋轉三維視角"
            onClick={() => setYaw((value) => value - 10)}
          >
            <FiArrowLeft
              className="size-3.5 shrink-0"
              aria-hidden="true"
            />
            左
          </Button>
          <span className="grid place-items-center text-xs font-black text-neutral-400">
            {yaw}° / {pitch}°
          </span>
          <Button
            className="min-h-9 px-3 text-xs"
            aria-label="向右旋轉三維視角"
            onClick={() => setYaw((value) => value + 10)}
          >
            <FiArrowRight
              className="size-3.5 shrink-0"
              aria-hidden="true"
            />
            右
          </Button>
          <span />
          <Button
            className="min-h-9 px-3 text-xs"
            aria-label="降低三維視角"
            onClick={() => setPitch((value) => Math.max(-80, value - 10))}
          >
            <FiArrowDown
              className="size-3.5 shrink-0"
              aria-hidden="true"
            />
            下
          </Button>
          <span />
        </div>
      </div>

      <div className="flex flex-wrap gap-3 text-xs font-semibold text-neutral-400">
        <span><i className="mr-1 inline-block size-2 rounded-full bg-neutral-400" />頂+側基準</span>
        {refinedPoints.length ? (
          <span><i className="mr-1 inline-block size-2 rounded-full bg-emerald-300" />頂+側+環繞精修</span>
        ) : null}
        <span><i className="mr-1 inline-block size-2 rounded-full bg-white" />人工點</span>
        <span><i className="mr-1 inline-block size-2 rounded-full bg-rose-400" />高誤差點</span>
        <span>同時屬於人工與高誤差時，以玫瑰色白框顯示。</span>
      </div>
      <dl className="grid gap-2 text-xs font-semibold text-neutral-400 min-[720px]:grid-cols-4">
        <div>
          <dt className="font-black text-neutral-300">原點</dt>
          <dd className="mt-1">{calibration?.world_coordinate_system?.origin || "植物基部中心"}</dd>
        </div>
        <div>
          <dt className="font-black text-neutral-300">X 軸</dt>
          <dd className="mt-1">{calibration?.world_coordinate_system?.x_axis || "水平方向"}</dd>
        </div>
        <div>
          <dt className="font-black text-neutral-300">Y 軸</dt>
          <dd className="mt-1">{calibration?.world_coordinate_system?.y_axis || "水平深度方向"}</dd>
        </div>
        <div>
          <dt className="font-black text-neutral-300">Z 軸／單位</dt>
          <dd className="mt-1">
            {calibration?.world_coordinate_system?.z_axis || "垂直向上"}／{calibration?.world_coordinate_system?.unit || "mm"}
          </dd>
        </div>
      </dl>
    </InnerPanel>
  );
}

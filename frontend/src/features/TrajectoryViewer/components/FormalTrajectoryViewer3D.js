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
import SubsectionHeader from "@/components/headers/SubsectionHeader";
import InnerPanel from "@/components/panels/InnerPanel";

import {
  formalTrajectoryModeColors,
  projectWorldTrajectory,
  trajectoryPolyline,
} from "../lib/trajectoryUtils";

const VIEW_WIDTH = 900;
const VIEW_HEIGHT = 520;
function finitePoint(item) {
  return item?.valid === true
    && [item.x_mm, item.y_mm, item.z_mm].every((value) => (
      Number.isFinite(Number(value))
    ));
}

function trajectorySegments(points) {
  const segments = [];
  let current = [];
  let previous = null;
  for (const point of points) {
    if (
      previous
      && (
        point.mode_id !== previous.mode_id
        || point.point_index !== previous.point_index + 1
        || point.missing_segment
      )
    ) {
      if (current.length) segments.push(current);
      current = [];
    }
    current.push(point);
    previous = point;
  }
  if (current.length) segments.push(current);
  return segments;
}

export default function FormalTrajectoryViewer3D({
  trajectory,
}) {
  const [yaw, setYaw] = useState(35);
  const [pitch, setPitch] = useState(25);
  const valid = trajectory.filter(finitePoint).map((item) => ({
    ...item,
    x: Number(item.x_mm),
    y: Number(item.y_mm),
    z: Number(item.z_mm),
  }));
  const modes = [...new Set(valid.map((item) => item.mode_id))];
  const colorByMode = formalTrajectoryModeColors(valid);
  const projected = projectWorldTrajectory(
    valid,
    [
      {
        id: "origin",
        label: "ArUco 世界原點",
        point: [0, 0, 0],
        color: "#ffffff",
      },
    ],
    {
      yawDegrees: yaw,
      pitchDegrees: pitch,
      width: VIEW_WIDTH,
      height: VIEW_HEIGHT,
    },
  );
  const segments = trajectorySegments(projected.points);

  return (
    <InnerPanel>
      <SubsectionHeader
        title="跨 Round 尖端標記軌跡"
        description="每個捕捉模式使用獨立系列；無效 Round 形成缺口，不會跨模式或跨缺口連線。"
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

      {valid.length ? (
        <div className="grid gap-3 min-[980px]:grid-cols-[minmax(0,1fr)_auto]">
          <div className="aspect-[16/9] min-w-0 overflow-hidden rounded-xl border border-white/15 bg-black/30">
            <svg
              className="size-full"
              viewBox={`0 0 ${VIEW_WIDTH} ${VIEW_HEIGHT}`}
              role="img"
              aria-label="跨 Round 三維尖端標記軌跡"
            >
              {segments.map((segment) => (
                <polyline
                  key={`${segment[0].mode_id}-${segment[0].point_index}`}
                  points={trajectoryPolyline(segment)}
                  fill="none"
                  stroke={colorByMode[segment[0].mode_id]}
                  strokeWidth="3"
                  strokeOpacity="0.9"
                />
              ))}
              {projected.points.map((point) => (
                <circle
                  key={`${point.mode_id}-${point.point_index}`}
                  cx={point.plotX}
                  cy={point.plotY}
                  r={point.manually_corrected ? 6 : 4}
                  fill={point.manually_corrected
                    ? "#ffffff"
                    : colorByMode[point.mode_id]
                  }
                  stroke={colorByMode[point.mode_id]}
                  strokeWidth={point.manually_corrected ? "3" : "1.5"}
                >
                  <title>
                    {`${point.mode_id} / ${point.round_id}・X ${point.x.toFixed(3)}・Y ${point.y.toFixed(3)}・Z ${point.z.toFixed(3)} mm・信心 ${(Number(point.confidence) * 100).toFixed(1)}%`}
                  </title>
                </circle>
              ))}
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
              <FiArrowUp aria-hidden="true" />
              上
            </Button>
            <span />
            <Button
              className="min-h-9 px-3 text-xs"
              aria-label="向左旋轉三維視角"
              onClick={() => setYaw((value) => value - 10)}
            >
              <FiArrowLeft aria-hidden="true" />
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
              <FiArrowRight aria-hidden="true" />
              右
            </Button>
            <span />
            <Button
              className="min-h-9 px-3 text-xs"
              aria-label="降低三維視角"
              onClick={() => setPitch((value) => Math.max(-80, value - 10))}
            >
              <FiArrowDown aria-hidden="true" />
              下
            </Button>
            <span />
          </div>
        </div>
      ) : (
        <p className="m-0 rounded-xl border border-dashed border-white/15 bg-black/15 p-5 text-center text-sm font-semibold text-neutral-400">
          本次分析沒有可顯示的有效三維尖端標記。
        </p>
      )}

      <div className="flex flex-wrap gap-3 text-xs font-semibold text-neutral-400">
        {modes.map((modeId) => (
          <span key={modeId}>
            <i
              className="mr-1 inline-block size-2 rounded-full"
              style={{
                backgroundColor: colorByMode[modeId],
              }}
            />
            {modeId}
          </span>
        ))}
        <span>
          <i className="mr-1 inline-block size-2 rounded-full bg-white" />
          人工修正
        </span>
      </div>
    </InnerPanel>
  );
}

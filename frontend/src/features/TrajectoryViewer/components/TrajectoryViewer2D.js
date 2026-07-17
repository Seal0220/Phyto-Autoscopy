"use client";

import {
  useEffect,
  useState,
} from "react";
import { FiRefreshCw } from "react-icons/fi";

import Button from "@/components/buttons/Button";
import InnerPanel from "@/components/panels/InnerPanel";
import SubsectionHeader from "@/components/headers/SubsectionHeader";
import { epipolarSegment } from "@/lib/imageGeometryUtils";

import {
  DETECTION_META,
} from "../lib/trajectoryUtils";

export default function TrajectoryViewer2D({
  analysisId,
  cameraId,
  imageHeight,
  imageWidth,
  overlay,
  trajectory,
}) {
  const [imageError, setImageError] = useState(false);
  const [imageToken, setImageToken] = useState(0);
  const xKey = cameraId === "top" ? "topX" : "sideX";
  const yKey = cameraId === "top" ? "topY" : "sideY";
  const typeKey = cameraId === "top" ? "topType" : "sideType";
  const cameraLabel = cameraId === "top" ? "俯視角" : "側視角";
  const width = Number(imageWidth) > 0
    ? Number(imageWidth)
    : Math.max(1, ...trajectory.map((point) => point[xKey] + 20));
  const height = Number(imageHeight) > 0
    ? Number(imageHeight)
    : Math.max(1, ...trajectory.map((point) => point[yKey] + 20));
  const lastFrame = trajectory.at(-1)?.frameId;
  const imageUrl = overlay?.imageUrl || (
    lastFrame
      ? `/api/analysis/${encodeURIComponent(analysisId)}/frames/${encodeURIComponent(lastFrame)}/images/${cameraId}`
      : ""
  );
  const polyline = trajectory.map((point) => (
    `${point[xKey]},${point[yKey]}`
  )).join(" ");
  const minimumPath = overlay?.minimumPath || [];
  const minimumPathPoints = minimumPath.map((point) => (
    `${point.x},${point.y}`
  )).join(" ");
  const line = epipolarSegment(
    overlay?.epipolarLine,
    width,
    height,
  );

  useEffect(() => {
    setImageError(false);
    setImageToken(0);
  }, [imageUrl]);

  return (
    <InnerPanel>
      <SubsectionHeader
        title={`${cameraLabel}二維軌跡`}
        description={cameraId === "side"
          ? "軌跡覆蓋於最後一個有效影格，並顯示對極線與最短路徑。"
          : "軌跡覆蓋於最後一個有效影格；各點依最終偵測來源分色。"
        }
      />

      <div className="relative aspect-video overflow-hidden rounded-xl border border-white/10 bg-black/40">
        <svg
          className="size-full"
          viewBox={`0 0 ${width} ${height}`}
          preserveAspectRatio="xMidYMid meet"
          role="img"
          aria-label={`${cameraLabel}植物尖端二維軌跡`}
        >
          {imageUrl && !imageError ? (
            <image
              key={`${imageUrl}-${imageToken}`}
              href={imageUrl}
              width={width}
              height={height}
              preserveAspectRatio="xMidYMid meet"
              onError={() => setImageError(true)}
            />
          ) : null}
          <polyline
            points={polyline}
            fill="none"
            stroke="#d4d4d8"
            strokeWidth="2"
            strokeOpacity="0.65"
            vectorEffect="non-scaling-stroke"
          />
          {line ? (
            <line
              x1={line[0].x}
              y1={line[0].y}
              x2={line[1].x}
              y2={line[1].y}
              stroke="#fda4af"
              strokeWidth="2"
              strokeDasharray="8 6"
              vectorEffect="non-scaling-stroke"
            />
          ) : null}
          {minimumPath.length > 1 ? (
            <polyline
              points={minimumPathPoints}
              fill="none"
              stroke="#fde68a"
              strokeWidth="2.5"
              vectorEffect="non-scaling-stroke"
            />
          ) : null}
          {trajectory.map((point) => {
            const meta = DETECTION_META[point[typeKey]] || DETECTION_META.Missing;
            return (
              <circle
                key={`${cameraId}-${point.frameId}`}
                cx={point[xKey]}
                cy={point[yKey]}
                r="4"
                fill={meta.color}
                stroke="#052e22"
                strokeWidth="1.5"
                vectorEffect="non-scaling-stroke"
              >
                <title>{`影格 ${point.frameId} · ${meta.label}`}</title>
              </circle>
            );
          })}
        </svg>

        {imageError ? (
          <div className="absolute top-3 right-3">
            <Button
              className="min-h-9 px-3 text-xs"
              onClick={() => {
                setImageError(false);
                setImageToken((value) => value + 1);
              }}
            >
              <FiRefreshCw
                className="size-3.5 shrink-0"
                aria-hidden="true"
              />
              重載底圖
            </Button>
          </div>
        ) : null}
      </div>

      {cameraId === "side" && (line || minimumPath.length > 1) ? (
        <div className="flex flex-wrap gap-3 text-xs font-semibold text-neutral-400">
          {line ? (
            <span className="inline-flex items-center gap-1.5">
              <i
                className="inline-block h-0.5 w-4 bg-rose-300"
                aria-hidden="true"
              />
              對極線（Epipolar Line）
            </span>
          ) : null}
          {minimumPath.length > 1 ? (
            <span className="inline-flex items-center gap-1.5">
              <i
                className="inline-block h-0.5 w-4 bg-amber-200"
                aria-hidden="true"
              />
              最短路徑（Minimum Path）
            </span>
          ) : null}
        </div>
      ) : null}
    </InnerPanel>
  );
}

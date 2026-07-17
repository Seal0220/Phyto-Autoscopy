"use client";

import {
  useEffect,
  useRef,
  useState,
} from "react";
import { FiRefreshCw } from "react-icons/fi";

import Button from "@/components/buttons/Button";
import { StatusPill } from "@/components/panels/Panel";

import {
  detectionTypeLabel,
  epipolarSegment,
  pointInsideImage,
} from "../lib/tipReviewUtils";

function pointString(points) {
  return points.map((point) => `${point.x},${point.y}`).join(" ");
}

function OverlayPoint({
  point,
  radius,
  fill,
  stroke,
  label,
}) {
  if (!point) return null;
  return (
    <circle
      cx={point.x}
      cy={point.y}
      r={radius}
      fill={fill}
      stroke={stroke}
      strokeWidth="2"
      vectorEffect="non-scaling-stroke"
      aria-label={label}
    />
  );
}

export default function TipReviewCanvas({
  active,
  cameraId,
  disabled = false,
  draft,
  imageUrl,
  storedDetection,
  onActivate,
  onPointChange,
}) {
  const [naturalSize, setNaturalSize] = useState(null);
  const [imageError, setImageError] = useState("");
  const [imageToken, setImageToken] = useState(0);
  const svgRef = useRef(null);
  const draggingRef = useRef(false);
  const automatic = storedDetection?.automatic;
  const finalDetection = storedDetection?.resolved
    || storedDetection?.interpolated
    || automatic;
  const cameraLabel = cameraId === "top" ? "俯視角" : "側視角";
  const width = naturalSize?.width || 1;
  const height = naturalSize?.height || 1;
  const line = epipolarSegment(
    automatic?.epipolarLine || finalDetection?.epipolarLine,
    width,
    height,
  );

  useEffect(() => {
    setNaturalSize(null);
    setImageError("");
    setImageToken(0);
  }, [imageUrl]);

  function imagePointFromEvent(event) {
    const svg = svgRef.current;
    const matrix = svg?.getScreenCTM();
    if (!svg || !matrix) return null;
    const point = svg.createSVGPoint();
    point.x = event.clientX;
    point.y = event.clientY;
    const transformed = point.matrixTransform(matrix.inverse());
    const next = {
      x: Number(transformed.x.toFixed(3)),
      y: Number(transformed.y.toFixed(3)),
    };
    return pointInsideImage(next, width, height) ? next : null;
  }

  function beginEditing(event) {
    if (disabled || !naturalSize) return;
    const point = imagePointFromEvent(event);
    if (!point) return;
    event.currentTarget.setPointerCapture(event.pointerId);
    draggingRef.current = true;
    onActivate(cameraId);
    onPointChange(cameraId, point);
  }

  function continueEditing(event) {
    if (!draggingRef.current || !naturalSize) return;
    const point = imagePointFromEvent(event);
    if (point) onPointChange(cameraId, point);
  }

  function finishEditing(event) {
    draggingRef.current = false;
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
  }

  return (
    <article
      className={`grid min-w-0 gap-3 rounded-[22px] border bg-white/6 p-3 shadow-[inset_0_1px_0_rgba(255,255,255,0.07)] transition-[background-color,border-color,filter,opacity] duration-150 ${active ? "border-emerald-200/60 bg-emerald-500/10" : "border-white/10"} ${disabled ? "grayscale opacity-60" : ""}`}
    >
      <div className="flex min-w-0 flex-wrap items-center justify-between gap-2">
        <h3 className="m-0 text-base font-black text-white">{cameraLabel}</h3>
        <div className="flex flex-wrap items-center gap-2">
          <StatusPill tone={active ? "success" : "neutral"}>
            {active ? "編輯中" : "檢視"}
          </StatusPill>
          <StatusPill tone={finalDetection?.valid ? "success" : "warning"}>
            {detectionTypeLabel(finalDetection?.detectionType)}
          </StatusPill>
        </div>
      </div>

      <div
        className="relative aspect-video min-w-0 overflow-hidden rounded-xl border border-white/10 bg-black/40 focus-within:border-emerald-200/60"
        tabIndex={0}
        role="application"
        aria-label={`${cameraLabel}尖端修正畫布；點擊或拖曳可指定位置`}
        onFocus={() => onActivate(cameraId)}
      >
        {imageUrl ? (
          <img
            key={`${imageUrl}-${imageToken}`}
            className="absolute inset-0 size-full object-contain"
            src={imageUrl}
            alt={`${cameraLabel}原始影像`}
            draggable="false"
            onLoad={(event) => {
              setNaturalSize({
                width: event.currentTarget.naturalWidth,
                height: event.currentTarget.naturalHeight,
              });
              setImageError("");
            }}
            onError={() => {
              setNaturalSize(null);
              setImageError(`${cameraLabel}原始影像載入失敗。`);
            }}
          />
        ) : (
          <div className="absolute inset-0 grid place-items-center p-4 text-sm font-semibold text-neutral-500">
            此影格沒有{cameraLabel}影像
          </div>
        )}

        {naturalSize ? (
          <svg
            ref={svgRef}
            className={`absolute inset-0 size-full touch-none ${disabled ? "cursor-not-allowed" : "cursor-crosshair"}`}
            viewBox={`0 0 ${width} ${height}`}
            preserveAspectRatio="xMidYMid meet"
            aria-label={`${cameraLabel}偵測覆蓋層`}
            onPointerDown={beginEditing}
            onPointerMove={continueEditing}
            onPointerUp={finishEditing}
            onPointerCancel={finishEditing}
            onLostPointerCapture={() => {
              draggingRef.current = false;
            }}
          >
            {automatic?.contour.length > 1 ? (
              <polyline
                points={pointString(automatic.contour)}
                fill="none"
                stroke="#6ee7b7"
                strokeWidth="1.5"
                strokeOpacity="0.75"
                vectorEffect="non-scaling-stroke"
              />
            ) : null}
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
            {automatic?.minimumPath.length > 1 ? (
              <polyline
                points={pointString(automatic.minimumPath)}
                fill="none"
                stroke="#fde68a"
                strokeWidth="2.5"
                vectorEffect="non-scaling-stroke"
              />
            ) : null}
            {automatic?.candidatePoints.map((
              point,
              index,
            ) => (
              <OverlayPoint
                key={`${point.x}-${point.y}-${index}`}
                point={point}
                radius="4"
                fill="#d4d4d8"
                stroke="#171717"
                label={`候選點 ${index + 1}`}
              />
            ))}
            <OverlayPoint
              point={automatic?.selectedPoint}
              radius="6"
              fill="#fbbf24"
              stroke="#451a03"
              label="自動尖端位置"
            />
            <OverlayPoint
              point={finalDetection?.selectedPoint}
              radius="7"
              fill="#34d399"
              stroke="#022c22"
              label="最終尖端位置"
            />
            {draft?.point && !draft.invalid ? (
              <circle
                cx={draft.point.x}
                cy={draft.point.y}
                r="10"
                fill="none"
                stroke="#ffffff"
                strokeWidth="2"
                strokeDasharray="4 3"
                vectorEffect="non-scaling-stroke"
                aria-label="人工修正草稿位置"
              />
            ) : null}
          </svg>
        ) : null}

        {imageError ? (
          <div className="absolute inset-0 grid place-items-center gap-3 bg-[#07130f]/95 p-4 text-center">
            <p className="m-0 text-sm font-semibold text-rose-200">
              {imageError}
            </p>
            <Button
              className="min-h-9 px-3 text-xs"
              onClick={() => {
                setImageError("");
                setImageToken((value) => value + 1);
              }}
            >
              <FiRefreshCw
                className="size-3.5 shrink-0"
                aria-hidden="true"
              />
              重新載入影像
            </Button>
          </div>
        ) : null}
      </div>

      <div className="grid gap-1 text-xs font-semibold text-neutral-400">
        <p className="m-0">
          自動：{automatic?.selectedPoint ? `${automatic.selectedPoint.x.toFixed(1)}, ${automatic.selectedPoint.y.toFixed(1)} px` : "—"}
        </p>
        <p className="m-0">
          最終：{finalDetection?.selectedPoint ? `${finalDetection.selectedPoint.x.toFixed(1)}, ${finalDetection.selectedPoint.y.toFixed(1)} px` : "—"}
        </p>
        {automatic?.statusReason ? (
          <p className="m-0 text-amber-200">{automatic.statusReason}</p>
        ) : null}
      </div>
    </article>
  );
}

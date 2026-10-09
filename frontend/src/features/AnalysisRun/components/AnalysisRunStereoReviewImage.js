"use client";

import { useRef, useState } from "react";
import FullscreenImage from "@/components/media/FullscreenImage";
import RetryMessage from "@/components/feedback/RetryMessage";
import { ANALYSIS_CAMERA_LABELS } from "@/features/Analysis/analysisConfig";
import { analysisViewImageUrl } from "@/lib/analysisImageUtils";
import {
  stereoImagePoint,
  stereoPairCheck,
  stereoPairLabel,
} from "../lib/analysisStereoReviewUtils";

export default function AnalysisRunStereoReviewImage({
  analysisId,
  view,
  pairs,
  selected,
  validation,
  disabled,
  onPointChange,
  onPairRemove,
}) {
  const width = view.image_width;
  const height = view.image_height;
  const camera = view.camera_id;
  const label = ANALYSIS_CAMERA_LABELS[camera];
  const markerScale = width / 960;
  const [ready, setReady] = useState(false);
  const [failed, setFailed] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const drag = useRef(null);
  const url = analysisViewImageUrl(analysisId, view.view_id, "undistorted");
  function finishDrag(
    event,
    restore = false,
  ) {
    const previous = drag.current;
    if (!previous) return;
    drag.current = null;
    if (restore && !disabled) onPointChange(camera, previous.origin, previous.index);
    if (event.currentTarget.hasPointerCapture(previous.pointerId)) {
      event.currentTarget.releasePointerCapture(previous.pointerId);
    }
  }
  const overlay = (
    <svg
      className={`absolute inset-0 size-full outline-offset-2 focus-visible:outline-2 focus-visible:outline-emerald-300 ${disabled ? "cursor-default" : "cursor-crosshair"}`}
      viewBox={`0 0 ${width} ${height}`}
      role="application"
      aria-label={`${label}共同位置標記：拖動調整，右鍵刪除此組；方向鍵微調第 ${selected + 1} 點，Enter 在中心新增，Delete 刪除此組`}
      tabIndex={disabled ? -1 : 0}
      onPointerDown={(event) => {
        if (disabled || event.button !== 0 || !event.isPrimary) return;
        const point = stereoImagePoint(
          event.clientX,
          event.clientY,
          event.currentTarget.getBoundingClientRect(),
          width,
          height,
        );
        if (!point) return;
        const marker = event.target.closest("[data-stereo-pair]");
        const index = marker ? Number(marker.dataset.stereoPair) : selected;
        const origin = marker ? pairs[index][camera] : point;
        drag.current = {
          index, pointerId: event.pointerId, origin,
          offsetX: point.x_px - origin.x_px,
          offsetY: point.y_px - origin.y_px,
        };
        event.preventDefault();
        event.currentTarget.focus({ preventScroll: true });
        event.currentTarget.setPointerCapture(event.pointerId);
        onPointChange(camera, origin, index);
      }}
      onPointerMove={(event) => {
        if (disabled || !drag.current || drag.current.pointerId !== event.pointerId) return;
        const point = stereoImagePoint(event.clientX, event.clientY, event.currentTarget.getBoundingClientRect(), width, height);
        if (!point) return;
        event.preventDefault();
        onPointChange(camera, {
          x_px: Math.max(0, Math.min(width - 1, point.x_px - drag.current.offsetX)),
          y_px: Math.max(0, Math.min(height - 1, point.y_px - drag.current.offsetY)),
        }, drag.current.index);
      }}
      onPointerUp={(event) => {
        if (drag.current?.pointerId !== event.pointerId) return;
        finishDrag(event);
      }}
      onPointerCancel={(event) => finishDrag(event, true)}
      onLostPointerCapture={() => { drag.current = null; }}
      onContextMenu={(event) => {
        const marker = event.target.closest("[data-stereo-pair]");
        if (!marker) return;
        event.preventDefault();
        finishDrag(event);
        if (!disabled) onPairRemove(Number(marker.dataset.stereoPair));
      }}
      onKeyDown={(event) => {
        if (event.key === "Escape" && drag.current) {
          event.preventDefault();
          finishDrag(event, true);
          return;
        }
        if (!disabled && ["Delete", "Backspace"].includes(event.key)) {
          event.preventDefault();
          const index = drag.current?.index ?? selected;
          finishDrag(event);
          onPairRemove(index);
          return;
        }
        if (disabled || !["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "Enter"].includes(event.key)) return;
        event.preventDefault();
        const current = pairs[selected]?.[camera] || { x_px: width / 2, y_px: height / 2 };
        const step = event.shiftKey ? 10 : 1;
        onPointChange(
          camera,
          {
            x_px: Math.max(0, Math.min(width - 1, current.x_px + (event.key === "ArrowLeft" ? -step : event.key === "ArrowRight" ? step : 0))),
            y_px: Math.max(0, Math.min(height - 1, current.y_px + (event.key === "ArrowUp" ? -step : event.key === "ArrowDown" ? step : 0))),
          },
        );
      }}
    >
      <rect
        width={width}
        height={height}
        fill="transparent"
      />
      {pairs.map((pair, index) => pair[camera] ? (
        <g
          key={index}
          data-stereo-pair={index}
          className={disabled ? "cursor-default" : "cursor-grab active:cursor-grabbing"}
        >
          <title>{stereoPairLabel(pair, index, validation, camera)}</title>
          <circle
            cx={pair[camera].x_px}
            cy={pair[camera].y_px}
            r={(index === selected ? 8 : 5) * markerScale}
            fill={stereoPairCheck(validation, index, camera) === "check" ? "#fbbf24" : index === selected ? "#34d399" : "#ffffff"}
            stroke="#06100c"
            strokeWidth={2 * markerScale}
          />
          <text
            x={pair[camera].x_px + 10 * markerScale}
            y={pair[camera].y_px - 10 * markerScale}
            fill="white"
            stroke="#06100c"
            strokeWidth={3 * markerScale}
            paintOrder="stroke"
            fontSize={24 * markerScale}
          >
            {index + 1}
          </text>
          <circle
            cx={pair[camera].x_px}
            cy={pair[camera].y_px}
            r={16 * markerScale}
            fill="transparent"
          />
        </g>
      ) : null)}
    </svg>
  );
  return (
    <article className="grid min-w-0 content-start gap-2">
      <h3 className="text-sm font-black text-white">{label}</h3>
      <div className="relative overflow-hidden rounded-xl bg-black">
        {/* 原生像素座標是幾何驗證的輸入。 */}
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          key={attempt}
          src={url}
          alt={`${label}去畸變影像，請配對同一個芽尖、葉尖、莖節或其他共同位置`}
          className="block h-auto w-full select-none"
          draggable="false"
          width={width}
          height={height}
          onLoad={() => { setReady(true); setFailed(false); }}
          onError={() => { setReady(false); setFailed(true); }}
        />
        {ready ? overlay : null}
        <FullscreenImage
          src={url}
          alt={`${label}共同位置配對`}
          label={`${label}共同位置配對`}
        >
          {overlay}
        </FullscreenImage>
      </div>
      {failed ? (
        <RetryMessage
          message={`${label}影像載入失敗，請重新載入。`}
          onRetry={() => { setFailed(false); setAttempt((previous) => previous + 1); }}
          retrying={false}
        />
      ) : null}
    </article>
  );
}

"use client";

import {
  useEffect,
  useState,
} from "react";
import { FiX } from "react-icons/fi";

import FullscreenImage from "@/components/media/FullscreenImage";
import { StatusPill } from "@/components/panels/Panel";
import { ANALYSIS_CAMERA_LABELS } from "@/features/Analysis/analysisConfig";
import { formatDateTime } from "@/lib/formatUtils";

import { formalViewImageUrl } from "../lib/formalTipReviewApiUtils";

function imagePoint(
  event,
  image,
) {
  const bounds = image.getBoundingClientRect();
  if (!bounds.width || !bounds.height || !image.naturalWidth || !image.naturalHeight) {
    return null;
  }
  return {
    x_px: Math.min(
      image.naturalWidth - 1,
      Math.max(0, ((event.clientX - bounds.left) / bounds.width) * image.naturalWidth),
    ),
    y_px: Math.min(
      image.naturalHeight - 1,
      Math.max(0, ((event.clientY - bounds.top) / bounds.height) * image.naturalHeight),
    ),
  };
}

export default function FormalTipReviewRoundImage({
  analysisId,
  view,
  point,
  viewIndex,
  disabled,
  onPointChange,
  onPointRemove,
}) {
  const [coordinateSpace, setCoordinateSpace] = useState("reprojection");
  const [dimensions, setDimensions] = useState({
    width: 0,
    height: 0,
  });
  const cameraLabel = ANALYSIS_CAMERA_LABELS[view.camera_id] || "未知視角";
  const imageUrl = formalViewImageUrl(
    analysisId,
    view.view_id,
    coordinateSpace,
  );

  useEffect(() => {
    setCoordinateSpace("reprojection");
    setDimensions({
      width: 0,
      height: 0,
    });
  }, [view.view_id]);

  return (
    <article className="grid min-w-0 gap-3 rounded-xl border border-white/15 bg-black/15 p-3">
      <div className="flex min-w-0 items-center justify-between gap-2">
        <div className="min-w-0">
          <h4 className="m-0 truncate text-sm font-black text-white">
            {cameraLabel}
          </h4>
          <p className="mt-1 m-0 truncate text-xs font-semibold text-neutral-500">
            {`影像 ${viewIndex + 1}・${formatDateTime(view.timestamp)}`}
          </p>
        </div>
        <StatusPill tone={point ? "success" : "neutral"}>
          {point ? "已指定" : "未指定"}
        </StatusPill>
      </div>

      <div
        className={`relative min-h-32 overflow-hidden rounded-xl border border-white/15 bg-black ${
          disabled ? "cursor-default" : "cursor-crosshair"
        }`}
        role="application"
        aria-label={`${cameraLabel}尖端位置選擇`}
        onPointerDown={(event) => {
          if (disabled || event.target.tagName !== "IMG") return;
          const resolved = imagePoint(event, event.target);
          if (resolved) onPointChange(view.view_id, resolved);
        }}
      >
        {/* 原生影像尺寸與指標座標是尖端標記運算的輸入。 */}
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          className="block h-auto w-full select-none"
          src={imageUrl}
          alt={`${cameraLabel}尖端標記重投影`}
          draggable="false"
          onLoad={(event) => setDimensions({
            width: event.currentTarget.naturalWidth,
            height: event.currentTarget.naturalHeight,
          })}
          onError={() => {
            if (coordinateSpace !== "undistorted") {
              setCoordinateSpace("undistorted");
            }
          }}
        />
        {point && dimensions.width > 0 && dimensions.height > 0 ? (
          <span
            className="pointer-events-none absolute size-4 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-white bg-emerald-400 shadow-[0_0_0_4px_rgba(16,185,129,0.3)]"
            style={{
              left: `${(point.x_px / dimensions.width) * 100}%`,
              top: `${(point.y_px / dimensions.height) * 100}%`,
            }}
            aria-hidden="true"
          />
        ) : null}
        <FullscreenImage
          src={imageUrl}
          alt={`${cameraLabel}尖端標記重投影`}
          label={`${cameraLabel}尖端標記`}
        />
      </div>

      <div className="flex min-w-0 items-center justify-between gap-2 text-xs font-bold text-neutral-400">
        <span className="min-w-0 truncate">
          {point
            ? `X ${point.x_px.toFixed(1)} / Y ${point.y_px.toFixed(1)} px`
            : disabled
              ? "目前未使用視角修正"
              : "點擊影像指定尖端"
          }
        </span>
        {point && !disabled ? (
          <button
            type="button"
            className="inline-flex shrink-0 cursor-pointer items-center gap-1 rounded-lg px-2 py-1 text-neutral-300 transition-colors duration-150 hover:bg-rose-500/15 hover:text-rose-200 focus-visible:outline-2 focus-visible:outline-emerald-300"
            onClick={() => onPointRemove(view.view_id)}
          >
            <FiX
              className="size-3.5"
              aria-hidden="true"
            />
            清除
          </button>
        ) : null}
      </div>
    </article>
  );
}

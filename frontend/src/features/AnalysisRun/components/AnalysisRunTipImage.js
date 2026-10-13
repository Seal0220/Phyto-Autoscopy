"use client";

import { useRef, useState } from "react";
import AnalysisRunImageFeatureMarkers from "./AnalysisRunImageFeatureMarkers";
import { tipMarkerSvg } from "../lib/analysisTipMarkerUtils";

function imagePoint(event, image) {
  const bounds = image?.getBoundingClientRect();
  if (!bounds?.width || !bounds.height || !image.naturalWidth || !image.naturalHeight) return null;
  return {
    x_px: Math.min(image.naturalWidth - 1, Math.max(0, (event.clientX - bounds.left) / bounds.width * image.naturalWidth)),
    y_px: Math.min(image.naturalHeight - 1, Math.max(0, (event.clientY - bounds.top) / bounds.height * image.naturalHeight)),
  };
}

export default function AnalysisRunTipImage({
  src,
  alt,
  viewId,
  cameraLabel,
  point,
  disabled,
  onPointChange,
  onPointRemove,
  onError,
  fullscreen = false,
  features,
  activeFeature,
  onActiveFeature,
}) {
  const imageRef = useRef(null);
  const dragRef = useRef(null);
  const [dimensions, setDimensions] = useState({ width: 0, height: 0 });
  const movePoint = (event) => {
    const resolved = imagePoint(event, imageRef.current);
    if (resolved) onPointChange?.(viewId, resolved);
  };
  return (
    <div
      className={`relative overflow-hidden rounded-xl border border-white/15 bg-black ${disabled ? "cursor-default" : "cursor-crosshair"}`}
      style={fullscreen ? { width: `min(100%, calc((100dvh - 2rem) * ${dimensions.width / dimensions.height || 1}))` } : undefined}
      aria-label={`${cameraLabel}尖端位置選擇`}
      onPointerDown={(event) => {
        if (!disabled && event.button === 0 && event.target === imageRef.current) movePoint(event);
      }}
    >
      {/* 原生影像矩形與尺寸用於精確換算影像座標，全螢幕亦維持相同比例。 */}
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        ref={imageRef}
        className="block h-auto w-full select-none"
        src={src}
        alt={alt}
        draggable={false}
        onLoad={(event) => setDimensions({ width: event.currentTarget.naturalWidth, height: event.currentTarget.naturalHeight })}
        onError={onError}
      />
      {point && dimensions.width > 0 && dimensions.height > 0 ? (
        <button
          type="button"
          aria-label={`${cameraLabel}尖端標記`}
          title="拖動尖端；右鍵或 Delete 清除"
          disabled={disabled}
          className="absolute z-20 size-9 -translate-x-1/2 -translate-y-1/2 touch-none rounded-full bg-transparent p-0 focus-visible:outline-2 focus-visible:outline-emerald-300"
          style={{ left: `${point.x_px / dimensions.width * 100}%`, top: `${point.y_px / dimensions.height * 100}%` }}
          onPointerDown={(event) => {
            if (disabled || event.button !== 0) return;
            event.preventDefault();
            dragRef.current = event.pointerId;
            event.currentTarget.setPointerCapture(event.pointerId);
          }}
          onPointerMove={(event) => {
            if (!disabled && dragRef.current === event.pointerId) movePoint(event);
          }}
          onPointerUp={(event) => {
            if (dragRef.current !== event.pointerId) return;
            dragRef.current = null;
            event.currentTarget.releasePointerCapture(event.pointerId);
          }}
          onLostPointerCapture={() => { dragRef.current = null; }}
          onContextMenu={(event) => {
            if (disabled) return;
            event.preventDefault();
            onPointRemove?.(viewId);
          }}
          onKeyDown={(event) => {
            if (disabled || !["Delete", "Backspace"].includes(event.key)) return;
            event.preventDefault();
            onPointRemove?.(viewId);
          }}
          dangerouslySetInnerHTML={{ __html: tipMarkerSvg({ interactive: !disabled }) }}
        />
      ) : null}
      <AnalysisRunImageFeatureMarkers
        features={features}
        viewId={viewId}
        width={dimensions.width}
        height={dimensions.height}
        activeFeature={activeFeature}
        onActiveFeature={onActiveFeature}
      />
    </div>
  );
}

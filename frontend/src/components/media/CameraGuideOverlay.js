"use client";

import { useRef } from "react";

const LOWER_HALF_METERING_CAMERAS = new Set([
  "side",
  "rotating",
]);

const HORIZONTAL_INSET_RATIO = 0.08;
const MINIMUM_REGION_SIZE = 0.05;
const KEYBOARD_RESIZE_STEP = 0.01;
const KEYBOARD_RESIZE_LARGE_STEP = 0.05;

const RESIZE_HANDLES = [
  {
    id: "nw",
    horizontal: "left",
    vertical: "top",
    cursorClassName: "cursor-nwse-resize",
    label: "調整測光區域左上角",
  },
  {
    id: "n",
    horizontal: "center",
    vertical: "top",
    cursorClassName: "cursor-ns-resize",
    label: "調整測光區域上邊",
  },
  {
    id: "ne",
    horizontal: "right",
    vertical: "top",
    cursorClassName: "cursor-nesw-resize",
    label: "調整測光區域右上角",
  },
  {
    id: "e",
    horizontal: "right",
    vertical: "center",
    cursorClassName: "cursor-ew-resize",
    label: "調整測光區域右邊",
  },
  {
    id: "se",
    horizontal: "right",
    vertical: "bottom",
    cursorClassName: "cursor-nwse-resize",
    label: "調整測光區域右下角",
  },
  {
    id: "s",
    horizontal: "center",
    vertical: "bottom",
    cursorClassName: "cursor-ns-resize",
    label: "調整測光區域下邊",
  },
  {
    id: "sw",
    horizontal: "left",
    vertical: "bottom",
    cursorClassName: "cursor-nesw-resize",
    label: "調整測光區域左下角",
  },
  {
    id: "w",
    horizontal: "left",
    vertical: "center",
    cursorClassName: "cursor-ew-resize",
    label: "調整測光區域左邊",
  },
];

function clamp(
  value,
  minimum,
  maximum,
) {
  return Math.min(maximum, Math.max(minimum, value));
}

function clampUnit(value) {
  return clamp(value, 0, 1);
}

function roundedRegion(region) {
  return Object.fromEntries(
    Object.entries(region).map(([key, value]) => [
      key,
      Number(value.toFixed(6)),
    ]),
  );
}

function normalizedRegion(region) {
  if (!region || typeof region !== "object") return null;

  const x = Number(region.x);
  const y = Number(region.y);
  const width = Number(region.width);
  const height = Number(region.height);
  if (![x, y, width, height].every(Number.isFinite)) return null;

  const normalizedX = clampUnit(x);
  const normalizedY = clampUnit(y);
  const normalizedWidth = Math.min(
    clampUnit(width),
    1 - normalizedX,
  );
  const normalizedHeight = Math.min(
    clampUnit(height),
    1 - normalizedY,
  );
  if (normalizedWidth <= 0 || normalizedHeight <= 0) return null;

  return {
    x: normalizedX,
    y: normalizedY,
    width: normalizedWidth,
    height: normalizedHeight,
  };
}

function fallbackMeteringRegion(cameraId) {
  const lowerHalf = LOWER_HALF_METERING_CAMERAS.has(cameraId);

  return {
    x: HORIZONTAL_INSET_RATIO,
    y: lowerHalf ? 0.5 : 0,
    width: 1 - HORIZONTAL_INSET_RATIO * 2,
    height: lowerHalf ? 0.5 : 1,
  };
}

function resizeRegion(
  region,
  handle,
  deltaX,
  deltaY,
) {
  let left = region.x;
  let top = region.y;
  let right = region.x + region.width;
  let bottom = region.y + region.height;

  if (handle.includes("w")) {
    left = clamp(
      region.x + deltaX,
      0,
      right - MINIMUM_REGION_SIZE,
    );
  }
  if (handle.includes("e")) {
    right = clamp(
      region.x + region.width + deltaX,
      left + MINIMUM_REGION_SIZE,
      1,
    );
  }
  if (handle.includes("n")) {
    top = clamp(
      region.y + deltaY,
      0,
      bottom - MINIMUM_REGION_SIZE,
    );
  }
  if (handle.includes("s")) {
    bottom = clamp(
      region.y + region.height + deltaY,
      top + MINIMUM_REGION_SIZE,
      1,
    );
  }

  return roundedRegion({
    x: left,
    y: top,
    width: right - left,
    height: bottom - top,
  });
}

function pointerPosition(event) {
  const svg = event.currentTarget.ownerSVGElement;
  const matrix = svg?.getScreenCTM();
  if (!svg || !matrix) return null;

  const point = svg.createSVGPoint();
  point.x = event.clientX;
  point.y = event.clientY;
  return point.matrixTransform(matrix.inverse());
}

function resizeHandlePosition(
  region,
  handle,
) {
  const left = region.x;
  const top = region.y;
  const right = region.x + region.width;
  const bottom = region.y + region.height;

  return {
    x: handle.horizontal === "left"
      ? left
      : handle.horizontal === "right"
        ? right
        : (left + right) / 2,
    y: handle.vertical === "top"
      ? top
      : handle.vertical === "bottom"
        ? bottom
        : (top + bottom) / 2,
  };
}

export default function CameraGuideOverlay({
  cameraId,
  crosshairVisible,
  exposureVisible,
  exposureEditable = false,
  frameWidth,
  frameHeight,
  meteringRegion,
  overexposedRegions,
  onMeteringRegionChange,
  onMeteringRegionCommit,
  onMeteringRegionCancel,
  className,
}) {
  const dragRef = useRef(null);
  const keyboardRegionRef = useRef(null);
  const sourceWidth = Number(frameWidth) > 0
    ? Number(frameWidth)
    : 16;
  const sourceHeight = Number(frameHeight) > 0
    ? Number(frameHeight)
    : 9;
  const activeMeteringRegion = normalizedRegion(meteringRegion)
    || fallbackMeteringRegion(cameraId);
  const activeOverexposedRegions = Array.isArray(overexposedRegions)
    ? overexposedRegions
      .map(normalizedRegion)
      .filter(Boolean)
    : [];
  const handleSize = Math.max(
    10,
    Math.min(sourceWidth, sourceHeight) * 0.03,
  );
  const hitSize = Math.max(36, handleSize * 2.2);

  function beginResize(
    event,
    handle,
  ) {
    if (!exposureEditable) return;
    const point = pointerPosition(event);
    if (!point) return;

    event.preventDefault();
    event.stopPropagation();
    event.currentTarget.setPointerCapture(event.pointerId);
    dragRef.current = {
      pointerId: event.pointerId,
      handle,
      startPoint: point,
      startRegion: activeMeteringRegion,
      currentRegion: activeMeteringRegion,
    };
    onMeteringRegionChange?.(activeMeteringRegion);
  }

  function continueResize(event) {
    const drag = dragRef.current;
    if (!drag || drag.pointerId !== event.pointerId) return;
    const point = pointerPosition(event);
    if (!point) return;

    event.preventDefault();
    const nextRegion = resizeRegion(
      drag.startRegion,
      drag.handle,
      (point.x - drag.startPoint.x) / sourceWidth,
      (point.y - drag.startPoint.y) / sourceHeight,
    );
    drag.currentRegion = nextRegion;
    onMeteringRegionChange?.(nextRegion);
  }

  function finishResize(event) {
    const drag = dragRef.current;
    if (!drag || drag.pointerId !== event.pointerId) return;

    event.preventDefault();
    event.stopPropagation();
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
    dragRef.current = null;
    onMeteringRegionCommit?.(drag.currentRegion);
  }

  function cancelResize(event) {
    const drag = dragRef.current;
    if (!drag || drag.pointerId !== event.pointerId) return;

    dragRef.current = null;
    onMeteringRegionCancel?.(drag.startRegion);
  }

  function resizeWithKeyboard(
    event,
    handle,
  ) {
    const arrows = new Set([
      "ArrowUp",
      "ArrowRight",
      "ArrowDown",
      "ArrowLeft",
    ]);
    if (!arrows.has(event.key) || !exposureEditable) return;

    event.preventDefault();
    const step = event.shiftKey
      ? KEYBOARD_RESIZE_LARGE_STEP
      : KEYBOARD_RESIZE_STEP;
    const deltaX = event.key === "ArrowLeft"
      ? -step
      : event.key === "ArrowRight"
        ? step
        : 0;
    const deltaY = event.key === "ArrowUp"
      ? -step
      : event.key === "ArrowDown"
        ? step
        : 0;
    const baseRegion = keyboardRegionRef.current
      || activeMeteringRegion;
    const nextRegion = resizeRegion(
      baseRegion,
      handle,
      deltaX,
      deltaY,
    );
    keyboardRegionRef.current = nextRegion;
    onMeteringRegionChange?.(nextRegion);
  }

  function commitKeyboardResize(event) {
    if (!event.key.startsWith("Arrow")) return;
    const region = keyboardRegionRef.current;
    if (!region) return;

    keyboardRegionRef.current = null;
    onMeteringRegionCommit?.(region);
  }

  function commitKeyboardResizeOnBlur() {
    const region = keyboardRegionRef.current;
    if (!region) return;

    keyboardRegionRef.current = null;
    onMeteringRegionCommit?.(region);
  }

  return (
    <div
      className={`pointer-events-none absolute inset-0 z-20 overflow-hidden ${className || ""}`}
      aria-hidden={exposureEditable ? undefined : "true"}
    >
      <svg
        className={`pointer-events-none absolute inset-0 size-full transition-opacity duration-150 motion-reduce:transition-none ${
          exposureVisible ? "opacity-100" : "opacity-0"
        }`}
        viewBox={`0 0 ${sourceWidth} ${sourceHeight}`}
        preserveAspectRatio="xMidYMid meet"
        aria-label={exposureEditable ? "可調整的測光區域" : undefined}
      >
        <rect
          x={activeMeteringRegion.x * sourceWidth}
          y={activeMeteringRegion.y * sourceHeight}
          width={activeMeteringRegion.width * sourceWidth}
          height={activeMeteringRegion.height * sourceHeight}
          fill="none"
          stroke="white"
          strokeWidth="1.5"
          strokeDasharray="7 5"
          vectorEffect="non-scaling-stroke"
          className="mix-blend-difference"
        />
        {activeOverexposedRegions.map((region, index) => (
          <rect
            key={`${region.x}-${region.y}-${region.width}-${region.height}-${index}`}
            x={region.x * sourceWidth}
            y={region.y * sourceHeight}
            width={region.width * sourceWidth}
            height={region.height * sourceHeight}
            rx={Math.max(2, Math.min(sourceWidth, sourceHeight) * 0.005)}
            fill="none"
            stroke="#34d399"
            strokeWidth="2"
            vectorEffect="non-scaling-stroke"
            className="drop-shadow-[0_0_4px_rgba(52,211,153,0.95)]"
          />
        ))}
        {exposureVisible && exposureEditable
          ? RESIZE_HANDLES.map((handle) => {
            const position = resizeHandlePosition(
              activeMeteringRegion,
              handle,
            );
            const centerX = position.x * sourceWidth;
            const centerY = position.y * sourceHeight;
            const horizontalEdge = ["n", "s"].includes(handle.id);
            const verticalEdge = ["e", "w"].includes(handle.id);
            const visibleWidth = horizontalEdge
              ? handleSize * 1.6
              : verticalEdge
                ? handleSize * 0.6
                : handleSize;
            const visibleHeight = verticalEdge
              ? handleSize * 1.6
              : horizontalEdge
                ? handleSize * 0.6
                : handleSize;

            return (
              <g
                className="focus:outline-none focus:[&_.metering-resize-handle]:stroke-emerald-300"
                key={handle.id}
                role="button"
                tabIndex={0}
                aria-label={handle.label}
                onPointerDown={(event) => beginResize(event, handle.id)}
                onPointerMove={continueResize}
                onPointerUp={finishResize}
                onPointerCancel={cancelResize}
                onKeyDown={(event) => resizeWithKeyboard(event, handle.id)}
                onKeyUp={commitKeyboardResize}
                onBlur={commitKeyboardResizeOnBlur}
              >
                <rect
                  x={centerX - hitSize / 2}
                  y={centerY - hitSize / 2}
                  width={hitSize}
                  height={hitSize}
                  fill="transparent"
                  className={`pointer-events-auto touch-none ${handle.cursorClassName}`}
                />
                <rect
                  x={centerX - visibleWidth / 2}
                  y={centerY - visibleHeight / 2}
                  width={visibleWidth}
                  height={visibleHeight}
                  fill="#07130f"
                  stroke="white"
                  strokeWidth="1.5"
                  vectorEffect="non-scaling-stroke"
                  className="metering-resize-handle pointer-events-none"
                />
              </g>
            );
          })
          : null
        }
      </svg>

      <span
        className={`absolute top-1/2 left-1/2 size-6 -translate-x-1/2 -translate-y-1/2 mix-blend-difference transition-opacity duration-150 motion-reduce:transition-none ${
          crosshairVisible ? "opacity-100" : "opacity-0"
        }`}
      >
        <span className="absolute top-1/2 left-0 h-px w-full -translate-y-1/2 bg-white" />
        <span className="absolute top-0 left-1/2 h-full w-px -translate-x-1/2 bg-white" />
      </span>
    </div>
  );
}

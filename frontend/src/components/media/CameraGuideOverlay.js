const LOWER_HALF_METERING_CAMERAS = new Set([
  "side",
  "rotating",
]);

const HORIZONTAL_INSET_RATIO = 0.08;

function clampUnit(value) {
  return Math.min(1, Math.max(0, value));
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

export default function CameraGuideOverlay({
  cameraId,
  crosshairVisible,
  exposureVisible,
  frameWidth,
  frameHeight,
  meteringRegion,
  overexposedRegions,
  className,
}) {
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

  return (
    <div
      className={`pointer-events-none absolute inset-0 z-20 overflow-hidden ${className || ""}`}
      aria-hidden="true"
    >
      <svg
        className={`absolute inset-0 size-full transition-opacity duration-150 motion-reduce:transition-none ${
          exposureVisible ? "opacity-100" : "opacity-0"
        }`}
        viewBox={`0 0 ${sourceWidth} ${sourceHeight}`}
        preserveAspectRatio="xMidYMid meet"
      >
        <rect
          x={activeMeteringRegion.x * sourceWidth}
          y={activeMeteringRegion.y * sourceHeight}
          width={activeMeteringRegion.width * sourceWidth}
          height={activeMeteringRegion.height * sourceHeight}
          rx={Math.max(4, Math.min(sourceWidth, sourceHeight) * 0.012)}
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

const LOWER_HALF_METERING_CAMERAS = new Set([
  "side",
  "rotating",
]);

export default function CameraGuideOverlay({
  cameraId,
  visible,
  className,
}) {
  const lowerHalfMetering = LOWER_HALF_METERING_CAMERAS.has(cameraId);

  return (
    <div
      className={`pointer-events-none absolute inset-0 z-20 overflow-hidden transition-opacity duration-150 motion-reduce:transition-none ${
        visible ? "opacity-100" : "opacity-0"
      } ${className || ""}`}
      aria-hidden="true"
    >
      <span
        className={`absolute border border-dashed border-white mix-blend-difference ${
          lowerHalfMetering
            ? "inset-x-0 top-1/2 bottom-0 rounded-b-2xl"
            : "inset-0 rounded-2xl"
        }`}
      />
      <span className="absolute top-1/2 left-1/2 size-6 -translate-x-1/2 -translate-y-1/2 mix-blend-difference">
        <span className="absolute top-1/2 left-0 h-px w-full -translate-y-1/2 bg-white" />
        <span className="absolute top-0 left-1/2 h-full w-px -translate-x-1/2 bg-white" />
      </span>
    </div>
  );
}

function translationFromMatrix(matrix) {
  if (!Array.isArray(matrix) || matrix.length !== 4) return null;
  const translation = [matrix[0]?.[3], matrix[1]?.[3], matrix[2]?.[3]].map(Number);
  return translation.every(Number.isFinite) ? translation : null;
}

function forwardFromMatrix(matrix) {
  if (!Array.isArray(matrix) || matrix.length !== 4) return null;
  const direction = [matrix[0]?.[2], matrix[1]?.[2]].map(Number);
  if (!direction.every(Number.isFinite)) return null;
  const length = Math.hypot(...direction);
  return length > 0
    ? [direction[0] / length, direction[1] / length]
    : null;
}

function normalizedPoints(profile) {
  const cameras = (profile?.cameras || []).flatMap((camera) => {
    const position = translationFromMatrix(camera.transform_world_from_camera);
    return position
      ? [{
        id: camera.camera_id,
        label: camera.position_label || camera.camera_id,
        position,
        forward: forwardFromMatrix(camera.transform_world_from_camera),
        kind: "camera",
      }]
      : [];
  });
  const trajectory = (profile?.quality?.rotation_samples || []).flatMap((sample) => {
    const position = translationFromMatrix(sample.observed_world_from_camera);
    return position
      ? [{
        id: sample.observation_id,
        label: `${Number(sample.angle_deg).toFixed(0)}°`,
        position,
        kind: "trajectory",
      }]
      : [];
  });
  const points = [...cameras, ...trajectory];
  if (!points.length) return [];
  const xs = points.map((point) => point.position[0]);
  const ys = points.map((point) => point.position[1]);
  const minimumX = Math.min(...xs);
  const maximumX = Math.max(...xs);
  const minimumY = Math.min(...ys);
  const maximumY = Math.max(...ys);
  const width = Math.max(1, maximumX - minimumX);
  const height = Math.max(1, maximumY - minimumY);

  return points.map((point) => ({
    ...point,
    x: 35 + ((point.position[0] - minimumX) / width) * 330,
    y: 215 - ((point.position[1] - minimumY) / height) * 180,
  }));
}

export default function CalibrationVisualization({ profile }) {
  const points = normalizedPoints(profile);

  return (
    <div className="grid gap-2">
      <h4 className="m-0 text-sm font-black text-emerald-200">
        世界座標與相機軌跡
      </h4>
      {points.length ? (
        <svg
          className="aspect-[8/5] w-full rounded-xl border border-white/15 bg-black/20"
          viewBox="0 0 400 250"
          role="img"
          aria-label="外參校正的相機位置、世界原點與旋臂軌跡俯視圖"
        >
          <line
            x1="28"
            y1="222"
            x2="82"
            y2="222"
            stroke="#6ee7b7"
            strokeWidth="2"
          />
          <line
            x1="28"
            y1="222"
            x2="28"
            y2="168"
            stroke="#a7f3d0"
            strokeWidth="2"
          />
          <text x="86" y="226" fill="#a3a3a3" fontSize="10">世界 X</text>
          <text x="12" y="162" fill="#a3a3a3" fontSize="10">世界 Y</text>
          {points.filter((point) => point.kind === "trajectory").map((point) => (
            <g key={point.id}>
              <circle
                cx={point.x}
                cy={point.y}
                r="4"
                fill="#fbbf24"
                opacity="0.8"
              />
              <text
                x={point.x + 6}
                y={point.y - 6}
                fill="#d4d4d4"
                fontSize="9"
              >
                {point.label}
              </text>
            </g>
          ))}
          {points.filter((point) => point.kind === "camera").map((point) => (
            <g key={point.id}>
              {point.forward ? (
                <line
                  x1={point.x}
                  y1={point.y}
                  x2={point.x + point.forward[0] * 22}
                  y2={point.y - point.forward[1] * 22}
                  stroke="#a7f3d0"
                  strokeWidth="2"
                  strokeLinecap="round"
                />
              ) : null}
              <path
                d={`M ${point.x} ${point.y - 7} L ${point.x - 7} ${point.y + 7} L ${point.x + 7} ${point.y + 7} Z`}
                fill="#6ee7b7"
                stroke="#ecfdf5"
                strokeWidth="1"
              />
              <text
                x={point.x + 9}
                y={point.y + 4}
                fill="#f5f5f5"
                fontSize="10"
              >
                {point.label}
              </text>
            </g>
          ))}
        </svg>
      ) : (
        <div className="grid min-h-40 place-items-center rounded-xl border border-white/15 bg-black/15 p-4 text-center text-sm font-semibold text-neutral-400">
          完成外參求解後，這裡會顯示相機視點、世界座標與旋臂軌跡。
        </div>
      )}
    </div>
  );
}

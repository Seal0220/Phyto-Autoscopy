import { FiCode, FiEye } from "react-icons/fi";

import { StatusPill } from "@/components/panels/Panel";

import CalibrationVisualization from "./CalibrationVisualization";

const QUALITY_LABELS = {
  excellent: "品質優良",
  acceptable: "品質通過",
  warning: "品質需檢查",
  failed: "品質未通過",
};

function qualityTone(value) {
  if (["excellent", "acceptable"].includes(value)) return "success";
  if (value === "failed") return "offline";
  return "warning";
}

function metric(value, unit = "") {
  const number = Number(value);
  return Number.isFinite(number) ? `${number.toFixed(3)}${unit}` : "—";
}

function MatrixBlock({
  label,
  value,
}) {
  if (!value) return null;

  return (
    <div className="grid min-w-0 gap-1">
      <h5 className="m-0 text-xs font-black text-neutral-300">
        {label}
      </h5>
      <pre className="m-0 max-w-full overflow-x-auto rounded-xl border border-white/15 bg-black/20 p-3 text-xs leading-5 text-neutral-300">
        {JSON.stringify(value, null, 2)}
      </pre>
    </div>
  );
}

export default function CalibrationQuality({ profile }) {
  const quality = profile?.quality || {};
  const graph = quality.observation_graph || {};

  return (
    <section className="grid gap-4">
      <div className="flex min-w-0 flex-wrap items-center gap-2">
        <FiEye
          className="size-4 text-emerald-200"
          aria-hidden="true"
        />
        <h4 className="m-0 mr-auto text-sm font-black text-white">
          品質與輸出
        </h4>
        <StatusPill tone={qualityTone(profile?.quality_status)}>
          {QUALITY_LABELS[profile?.quality_status] || "尚未計算"}
        </StatusPill>
      </div>

      <dl className="grid gap-3 text-sm min-[520px]:grid-cols-2 min-[900px]:grid-cols-4">
        <div>
          <dt className="text-xs font-black text-neutral-500">平均重投影誤差</dt>
          <dd className="mt-1 m-0 font-bold text-neutral-200">
            {metric(quality.mean_reprojection_error_px, " px")}
          </dd>
        </div>
        <div>
          <dt className="text-xs font-black text-neutral-500">最大重投影誤差</dt>
          <dd className="mt-1 m-0 font-bold text-neutral-200">
            {metric(quality.maximum_reprojection_error_px, " px")}
          </dd>
        </div>
        <div>
          <dt className="text-xs font-black text-neutral-500">旋轉軸擬合誤差</dt>
          <dd className="mt-1 m-0 font-bold text-neutral-200">
            {metric(quality.rotation_axis_fit_error_mm, " mm")}
          </dd>
        </div>
        <div>
          <dt className="text-xs font-black text-neutral-500">馬達角度殘差</dt>
          <dd className="mt-1 m-0 font-bold text-neutral-200">
            {metric(quality.motor_angle_residual_deg, "°")}
          </dd>
        </div>
        <div>
          <dt className="text-xs font-black text-neutral-500">旋臂軌跡圓度誤差</dt>
          <dd className="mt-1 m-0 font-bold text-neutral-200">
            {metric(quality.arm_path_circularity_error_mm, " mm")}
          </dd>
        </div>
        <div>
          <dt className="text-xs font-black text-neutral-500">世界尺度誤差</dt>
          <dd className="mt-1 m-0 font-bold text-neutral-200">
            {metric(quality.world_scale_error_mm, " mm")}
          </dd>
        </div>
        <div>
          <dt className="text-xs font-black text-neutral-500">共同觀測</dt>
          <dd className="mt-1 m-0 font-bold text-neutral-200">
            {quality.valid_shared_observation_count ?? 0} 組
          </dd>
        </div>
        <div>
          <dt className="text-xs font-black text-neutral-500">觀測圖</dt>
          <dd className="mt-1 m-0 font-bold text-neutral-200">
            {graph.connected ? `已連通，${graph.edge_count || 0} 條關係` : "尚未連通"}
          </dd>
        </div>
        <div>
          <dt className="text-xs font-black text-neutral-500">最佳化前誤差</dt>
          <dd className="mt-1 m-0 font-bold text-neutral-200">
            {metric(
              quality.global_optimization?.initial_rms_error_px,
              " px",
            )}
          </dd>
        </div>
        <div>
          <dt className="text-xs font-black text-neutral-500">最佳化後誤差</dt>
          <dd className="mt-1 m-0 font-bold text-neutral-200">
            {metric(
              quality.global_optimization?.final_rms_error_px,
              " px",
            )}
          </dd>
        </div>
      </dl>

      <CalibrationVisualization profile={profile} />

      <details className="group rounded-xl border border-white/15 bg-black/15">
        <summary className="flex cursor-pointer list-none items-center gap-2 px-4 py-3 text-sm font-black text-neutral-200 focus-visible:outline-2 focus-visible:outline-emerald-300">
          <FiCode
            className="size-4 text-emerald-200"
            aria-hidden="true"
          />
          進階資料（唯讀矩陣）
        </summary>
        <div className="grid gap-3 border-t border-white/15 p-4">
          {(profile?.cameras || []).map((camera) => (
            <div
              className="grid gap-3 min-[900px]:grid-cols-2"
              key={camera.camera_id}
            >
              <MatrixBlock
                label={`${camera.camera_id}：相機至裝置座標轉換`}
                value={camera.transform_rig_from_camera}
              />
              <MatrixBlock
                label={`${camera.camera_id}：相機至世界座標轉換`}
                value={camera.transform_world_from_camera}
              />
            </div>
          ))}
          <MatrixBlock
            label="裝置至世界座標轉換"
            value={profile?.world_alignment?.transform_world_from_rig}
          />
          <MatrixBlock
            label="旋轉軸原點"
            value={profile?.motion_model?.rotation_axis_origin_mm}
          />
          <MatrixBlock
            label="旋轉軸方向"
            value={profile?.motion_model?.rotation_axis_direction}
          />
          <MatrixBlock
            label="旋臂相機安裝轉換"
            value={profile?.motion_model?.mount_transform_from_camera}
          />
        </div>
      </details>
    </section>
  );
}

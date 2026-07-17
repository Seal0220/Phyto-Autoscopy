import SubsectionHeader from "@/components/headers/SubsectionHeader";

import {
  distortionNamed,
  formatCalibrationNumber,
} from "../lib/calibrationUtils";
import CalibrationMatrix from "./CalibrationMatrix";

function CalibrationDistortion({
  title,
  coefficients,
}) {
  return (
    <article className="grid min-w-0 content-start gap-3 rounded-xl border border-white/10 bg-black/10 p-3">
      <div>
        <h4 className="m-0 text-xs font-black text-emerald-200">{title}</h4>
        <p className="mt-1 text-[11px] font-semibold text-neutral-400">
          OpenCV 固定順序：k1、k2、p1、p2、k3
        </p>
      </div>
      {Array.isArray(coefficients) ? (
        <dl className="grid grid-cols-5 gap-px overflow-hidden rounded-lg border border-white/10 bg-white/10">
          {distortionNamed(coefficients).map((item) => (
            <div
              className="min-w-0 bg-[#0b1813] p-2 text-center"
              key={item.name}
            >
              <dt className="text-[10px] font-black text-neutral-500">{item.name}</dt>
              <dd className="mt-1 m-0 overflow-hidden text-ellipsis font-mono text-[11px] font-semibold text-neutral-200">
                {formatCalibrationNumber(item.value, 9)}
              </dd>
            </div>
          ))}
        </dl>
      ) : (
        <p className="m-0 text-sm font-semibold text-neutral-500">尚未產生</p>
      )}
    </article>
  );
}

export default function CalibrationMatrices({ profile }) {
  return (
    <div className="grid gap-4">
      <SubsectionHeader
        title="相機內參、畸變與雙目幾何"
        description="以下均為本次 OpenCV 計算與實測世界座標轉換的保存值。"
      />

      <section className="grid gap-3 min-[900px]:grid-cols-2">
        <CalibrationMatrix
          title="俯視角 Camera Matrix（K_top）"
          value={profile.top_camera_matrix}
        />
        <CalibrationDistortion
          title="俯視角 Distortion（D_top）"
          coefficients={profile.top_distortion_coefficients}
        />
        <CalibrationMatrix
          title="側視角 Camera Matrix（K_side）"
          value={profile.side_camera_matrix}
        />
        <CalibrationDistortion
          title="側視角 Distortion（D_side）"
          coefficients={profile.side_distortion_coefficients}
        />
      </section>

      <section className="grid gap-3 min-[900px]:grid-cols-2">
        <CalibrationMatrix
          title="相機間旋轉（R）"
          value={profile.rotation_matrix}
        />
        <CalibrationMatrix
          title="相機間平移（t）"
          value={profile.translation_vector}
          description="單位由實測雙目棋盤格尺寸決定。"
        />
        <CalibrationMatrix
          title="Essential Matrix（E）"
          value={profile.essential_matrix}
        />
        <CalibrationMatrix
          title="Fundamental Matrix（F）"
          value={profile.fundamental_matrix}
        />
        <CalibrationMatrix
          title="俯視角校正旋轉（R_top）"
          value={profile.top_rectification_rotation}
        />
        <CalibrationMatrix
          title="側視角校正旋轉（R_side）"
          value={profile.side_rectification_rotation}
        />
        <CalibrationMatrix
          title="俯視角投影（P_top）"
          value={profile.top_projection_matrix}
        />
        <CalibrationMatrix
          title="側視角投影（P_side）"
          value={profile.side_projection_matrix}
        />
        <CalibrationMatrix
          title="視差轉深度（Q）"
          value={profile.disparity_to_depth_matrix}
        />
        <CalibrationMatrix
          title="T_world_from_stereo"
          value={profile.world_transform_matrix}
          description="由使用者確認的 4 × 4 剛體世界座標轉換，不是論文推導值。"
        />
        <CalibrationMatrix
          title="俯視角 valid ROI"
          value={profile.top_valid_pixel_roi}
          description="順序：x、y、width、height"
        />
        <CalibrationMatrix
          title="側視角 valid ROI"
          value={profile.side_valid_pixel_roi}
          description="順序：x、y、width、height"
        />
      </section>
    </div>
  );
}

import StatusCard from "@/components/cards/StatusCard";
import SubsectionHeader from "@/components/headers/SubsectionHeader";
import InnerPanel from "@/components/panels/InnerPanel";
import { StatusPill } from "@/components/panels/Panel";

import {
  calibrationDateTime,
  calibrationStatus,
  formatCalibrationNumber,
} from "../lib/calibrationUtils";

function sizeLabel(value) {
  return Array.isArray(value) && value.length >= 2
    ? `${formatCalibrationNumber(value[0])} × ${formatCalibrationNumber(value[1])}`
    : "—";
}

function differenceLabel(value) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return "—";
  if (parsed === 0) return "相同";
  return `${parsed > 0 ? "+" : ""}${formatCalibrationNumber(parsed)} cm`;
}

const CAMERA_LABELS = {
  top: "俯視角",
  side: "側視角",
  rotating: "旋臂視角",
};

function projectionModelLabel(value) {
  if (value === "fisheye") return "Fisheye";
  if (value === "brown_pinhole") return "Brown／Pinhole";
  return "尚未評估";
}

export default function CalibrationSummary({ profile }) {
  const status = calibrationStatus(profile.status);
  const differences = profile.actual_measurement_difference || {};
  const selected = profile.selected_images || {};

  return (
    <div className="grid gap-4">
      <div className="grid gap-3 min-[520px]:grid-cols-3">
        <StatusCard
          title="校正狀態"
          content={status.label}
          note={profile.valid ? "可供分析選用" : "不可供新分析選用"}
        />
        <StatusCard
          title="影像解析度"
          content={profile.image_width && profile.image_height
            ? `${profile.image_width} × ${profile.image_height}`
            : "尚未求解"
          }
          note="俯視角／側視角需一致"
        />
        <StatusCard
          title="雙目重投影誤差"
          content={profile.stereo_mean_reprojection_error === null
            || profile.stereo_mean_reprojection_error === undefined
            ? "尚未計算"
            : `${formatCalibrationNumber(profile.stereo_mean_reprojection_error)} px`
          }
          note="僅為量測值，非品質保證"
        />
      </div>

      <div className="grid gap-4 min-[900px]:grid-cols-2">
        <InnerPanel as="section">
          <SubsectionHeader
            title="校正檔案與來源"
            description="來源影像只讀取，不會由校正流程修改。"
          >
            <StatusPill tone={status.tone}>{status.label}</StatusPill>
          </SubsectionHeader>
          <dl className="grid gap-3 text-sm min-[520px]:grid-cols-2">
            <div className="min-w-0">
              <dt className="text-xs font-black text-neutral-500">校正 ID</dt>
              <dd className="mt-1 m-0 break-all font-bold text-neutral-100">
                {profile.calibration_id}
              </dd>
            </div>
            <div className="min-w-0">
              <dt className="text-xs font-black text-neutral-500">建立時間</dt>
              <dd className="mt-1 m-0 font-bold text-neutral-100">
                {calibrationDateTime(profile.created_at)}
              </dd>
            </div>
            <div className="min-w-0">
              <dt className="text-xs font-black text-neutral-500">俯視角單目影像</dt>
              <dd className="mt-1 m-0 font-bold text-neutral-100">
                {selected.top?.length || 0} 張
              </dd>
            </div>
            <div className="min-w-0">
              <dt className="text-xs font-black text-neutral-500">側視角單目影像</dt>
              <dd className="mt-1 m-0 font-bold text-neutral-100">
                {selected.side?.length || 0} 張
              </dd>
            </div>
            <div className="min-w-0">
              <dt className="text-xs font-black text-neutral-500">雙目影像配對</dt>
              <dd className="mt-1 m-0 font-bold text-neutral-100">
                {selected.stereo?.length || 0} 組
              </dd>
            </div>
            <div className="min-w-0">
              <dt className="text-xs font-black text-neutral-500">旋臂視角單目影像</dt>
              <dd className="mt-1 m-0 font-bold text-neutral-100">
                {selected.rotating?.length || 0} 張
              </dd>
            </div>
            <div className="min-w-0">
              <dt className="text-xs font-black text-neutral-500">輸出位置</dt>
              <dd className="mt-1 m-0 break-all font-bold text-neutral-100">
                {profile.output_path || "—"}
              </dd>
            </div>
          </dl>
        </InnerPanel>

        <InnerPanel as="section">
          <SubsectionHeader
            title="世界座標定義"
            description="單位固定為 mm；實際方向由已量測的 T_world_from_stereo 決定。"
          />
          <dl className="grid gap-3 text-sm min-[520px]:grid-cols-2">
            <div>
              <dt className="text-xs font-black text-neutral-500">原點</dt>
              <dd className="mt-1 m-0 font-bold text-neutral-100">
                {profile.world_coordinate_system?.origin || "—"}
              </dd>
            </div>
            <div>
              <dt className="text-xs font-black text-neutral-500">X 軸</dt>
              <dd className="mt-1 m-0 font-bold text-neutral-100">
                {profile.world_coordinate_system?.x_axis || "—"}
              </dd>
            </div>
            <div>
              <dt className="text-xs font-black text-neutral-500">Y 軸</dt>
              <dd className="mt-1 m-0 font-bold text-neutral-100">
                {profile.world_coordinate_system?.y_axis || "—"}
              </dd>
            </div>
            <div>
              <dt className="text-xs font-black text-neutral-500">Z 軸</dt>
              <dd className="mt-1 m-0 font-bold text-neutral-100">
                {profile.world_coordinate_system?.z_axis || "—"}
              </dd>
            </div>
          </dl>
        </InnerPanel>
      </div>

      {Object.keys(profile.camera_projection_models || {}).length ? (
        <InnerPanel as="section">
          <SubsectionHeader
            title="鏡頭投影模型"
            description="以相同角點比較 Brown／Pinhole 與 OpenCV Fisheye 的重投影誤差及逐圖穩定度，再保存實際採用模型。"
          />
          <dl className="grid gap-3 min-[720px]:grid-cols-3">
            {Object.entries(CAMERA_LABELS).map(([cameraId, label]) => {
              const model = profile.camera_projection_models?.[cameraId];
              if (!model) return null;
              const selectedEvaluation = profile.camera_model_evaluations?.[
                cameraId
              ]?.[model];
              const imageSize = profile.camera_image_sizes?.[cameraId];

              return (
                <div
                  className="rounded-xl border border-white/10 bg-black/10 p-3"
                  key={cameraId}
                >
                  <dt className="text-xs font-black text-neutral-500">
                    {label}（{cameraId}）
                  </dt>
                  <dd className="mt-1 m-0 text-sm font-black text-neutral-100">
                    {projectionModelLabel(model)}
                  </dd>
                  <dd className="mt-1 m-0 text-xs font-semibold text-neutral-400">
                    {sizeLabel(imageSize)} px · 平均誤差 {selectedEvaluation
                      ? `${formatCalibrationNumber(
                        selectedEvaluation.mean_reprojection_error_px,
                      )} px`
                      : "—"
                    }
                  </dd>
                </div>
              );
            })}
          </dl>
        </InnerPanel>
      ) : null}

      <InnerPanel as="section">
        <SubsectionHeader
          title="論文基準與實際差異"
          description="A1／A2 數字是 Ruiz-Melero et al. 2024 的比較基準；雙目內角點與格距不是論文公開參數。"
        />
        <div className="grid gap-3 min-[720px]:grid-cols-2">
          <article className="grid gap-2 rounded-xl border border-white/10 bg-black/10 p-3 text-sm">
            <h4 className="m-0 text-sm font-black text-white">A1 單目校正</h4>
            <p className="m-0 font-semibold text-neutral-300">
              論文：10 × 7 內角點，59.4 × 84.1 cm
            </p>
            <p className="m-0 font-semibold text-neutral-300">
              實測：{sizeLabel(profile.chessboard_pattern)} 內角點，{sizeLabel(profile.individual_board_size_cm)} cm
            </p>
            <p className="m-0 text-xs font-semibold text-neutral-400">
              板面差異：寬 {differenceLabel(differences.individual_board_width_cm)}，高 {differenceLabel(differences.individual_board_height_cm)}；格距 {sizeLabel(profile.square_size_mm)} mm
            </p>
          </article>
          <article className="grid gap-2 rounded-xl border border-white/10 bg-black/10 p-3 text-sm">
            <h4 className="m-0 text-sm font-black text-white">A2 雙目校正</h4>
            <p className="m-0 font-semibold text-neutral-300">
              論文：42.0 × 59.4 cm；未公開內角點數與格距
            </p>
            <p className="m-0 font-semibold text-neutral-300">
              實測：{sizeLabel(profile.stereo_chessboard_pattern)} 內角點，{sizeLabel(profile.stereo_board_size_cm)} cm
            </p>
            <p className="m-0 text-xs font-semibold text-neutral-400">
              板面差異：寬 {differenceLabel(differences.stereo_board_width_cm)}，高 {differenceLabel(differences.stereo_board_height_cm)}；格距 {sizeLabel(profile.stereo_square_size_mm)} mm
            </p>
          </article>
        </div>
        {profile.notes ? (
          <p className="m-0 rounded-xl border border-white/10 bg-black/10 p-3 text-sm font-semibold text-neutral-300">
            備註：{profile.notes}
          </p>
        ) : null}
      </InnerPanel>

      {profile.potentially_invalid_reasons?.length ? (
        <div
          className="grid gap-2 rounded-xl border border-amber-200/30 bg-amber-500/10 p-4"
          role="alert"
        >
          <h3 className="m-0 text-sm font-black text-amber-200">校正可能失效</h3>
          <ul className="m-0 grid gap-1 pl-5 text-sm font-semibold text-amber-100">
            {profile.potentially_invalid_reasons.map((reason) => (
              <li key={reason}>{reason}</li>
            ))}
          </ul>
          <p className="m-0 text-xs font-semibold text-amber-200">
            舊校正檔案會保留，但不可供新分析選用；請使用目前相機與支架狀態重新校正。
          </p>
        </div>
      ) : null}

      {profile.manual_invalidation_reasons?.length ? (
        <div className="grid gap-2 rounded-xl border border-rose-300/30 bg-rose-500/10 p-4">
          <h3 className="m-0 text-sm font-black text-rose-200">人工失效原因</h3>
          <ul className="m-0 grid gap-1 pl-5 text-sm font-semibold text-rose-100">
            {profile.manual_invalidation_reasons.map((reason) => (
              <li key={reason}>{reason}</li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}

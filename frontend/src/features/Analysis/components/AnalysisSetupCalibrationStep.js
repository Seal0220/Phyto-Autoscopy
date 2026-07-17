import InnerPanel from "@/components/panels/InnerPanel";
import { StatusPill } from "@/components/panels/Panel";
import SubsectionHeader from "@/components/headers/SubsectionHeader";
import { formatDateTime } from "@/lib/formatUtils";

import AnalysisEmbeddedCalibration from "./AnalysisEmbeddedCalibration";

function errorValue(value) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? `${parsed.toFixed(3)} px` : "—";
}

export default function AnalysisSetupCalibrationStep({
  calibrations,
  source,
  method,
  selectedCalibrationId,
  onSelect,
  onProfileChange,
}) {
  const topResolution = source?.camera_resolutions?.top;
  const sideResolution = source?.camera_resolutions?.side;

  return (
    <section
      className="grid gap-4"
      aria-labelledby="analysis-calibration-step-title"
    >
      <SubsectionHeader
        titleId="analysis-calibration-step-title"
        title="選擇相機校正"
        description="校正會版本化並跨分析重用；分析解析度不同時會自動換算相機矩陣。"
      />

      <AnalysisEmbeddedCalibration
        onProfileChange={onProfileChange}
        onSelect={onSelect}
      />

      <div className="grid gap-3">
        {calibrations.length ? calibrations.map((calibration) => {
          const selected = calibration.calibration_id === selectedCalibrationId;
          const supportsMethod = method !== "top_side_rotating"
            || calibration.supports_rotating;
          const selectable = calibration.valid && supportsMethod;

          return (
            <label
              className={`grid min-w-0 gap-3 rounded-[22px] border p-4 transition-[background-color,border-color,opacity] duration-150 focus-within:outline-2 focus-within:outline-emerald-300 ${
                selectable
                  ? selected
                    ? "cursor-pointer border-emerald-200/75 bg-emerald-500/20"
                    : "cursor-pointer border-white/10 bg-white/6 hover:border-emerald-200/35 hover:bg-white/[0.09]"
                  : "cursor-not-allowed border-white/10 bg-black/10 opacity-60"
              }`}
              key={calibration.calibration_id}
            >
              <input
                className="sr-only"
                type="radio"
                name="analysis-calibration"
                value={calibration.calibration_id}
                checked={selected}
                disabled={!selectable}
                onChange={() => onSelect(calibration.calibration_id)}
              />

              <div className="flex min-w-0 flex-wrap items-center gap-2">
                <span className="min-w-0 break-all text-sm font-black tracking-widest text-white">
                  {calibration.calibration_id || "未命名校正"}
                </span>
                <StatusPill tone={selectable ? "success" : "offline"}>
                  {selectable ? "可使用" : "不可使用"}
                </StatusPill>
                {selected ? (
                  <StatusPill tone="success">已選擇</StatusPill>
                ) : null}
              </div>

              <dl className="grid gap-2 text-sm min-[520px]:grid-cols-2 min-[900px]:grid-cols-4">
                <div>
                  <dt className="text-xs font-black text-neutral-500">相機</dt>
                  <dd className="mt-1 m-0 font-bold text-neutral-200">
                    {calibration.supports_rotating
                      ? "俯視角 / 側視角 / 環繞視角"
                      : "俯視角 / 側視角"
                    }
                  </dd>
                </div>
                <div>
                  <dt className="text-xs font-black text-neutral-500">校正解析度</dt>
                  <dd className="mt-1 m-0 font-bold text-neutral-200">
                    {calibration.image_width && calibration.image_height
                      ? `${calibration.image_width} × ${calibration.image_height}`
                      : "—"
                    }
                  </dd>
                </div>
                <div>
                  <dt className="text-xs font-black text-neutral-500">分析解析度</dt>
                  <dd className="mt-1 m-0 font-bold text-neutral-200">
                    {topResolution && sideResolution
                      ? `俯視 ${topResolution.join(" × ")} / 側視 ${sideResolution.join(" × ")}`
                      : "建立分析時自動讀取"
                    }
                  </dd>
                </div>
                <div>
                  <dt className="text-xs font-black text-neutral-500">建立時間</dt>
                  <dd className="mt-1 m-0 font-bold text-neutral-200">
                    {formatDateTime(calibration.created_at)}
                  </dd>
                </div>
                <div>
                  <dt className="text-xs font-black text-neutral-500">雙目重投影誤差</dt>
                  <dd className="mt-1 m-0 font-bold text-neutral-200">
                    {errorValue(calibration.stereo_mean_reprojection_error)}
                  </dd>
                </div>
                <div>
                  <dt className="text-xs font-black text-neutral-500">俯視重投影誤差</dt>
                  <dd className="mt-1 m-0 font-bold text-neutral-200">
                    {errorValue(calibration.top_mean_reprojection_error)}
                  </dd>
                </div>
                <div>
                  <dt className="text-xs font-black text-neutral-500">側視重投影誤差</dt>
                  <dd className="mt-1 m-0 font-bold text-neutral-200">
                    {errorValue(calibration.side_mean_reprojection_error)}
                  </dd>
                </div>
              </dl>

              {!supportsMethod ? (
                <p className="m-0 text-xs font-semibold text-amber-200">
                  此校正缺少 rotating 旋轉軸、零度偏移與動態外參。
                </p>
              ) : null}

              {!calibration.valid && calibration.potentially_invalid_reasons.length ? (
                <ul className="m-0 grid gap-1 pl-5 text-xs font-semibold text-rose-200">
                  {calibration.potentially_invalid_reasons.map((reason) => (
                    <li key={reason}>{reason}</li>
                  ))}
                </ul>
              ) : null}

              {calibration.valid ? (
                <p className="m-0 text-xs font-semibold leading-5 text-neutral-400">
                  解析度不同時只換算本次分析使用的像素座標矩陣，不會修改原校正設定檔。
                  若相機解析度模式會裁切視野，實際精度仍取決於相機的裁切方式。
                </p>
              ) : null}
            </label>
          );
        }) : (
          <InnerPanel>
            <p className="m-0 py-4 text-center text-sm font-semibold text-neutral-400">
              尚無相機校正。請先建立並驗證俯視角與側視角的雙目校正。
            </p>
          </InnerPanel>
        )}
      </div>
    </section>
  );
}

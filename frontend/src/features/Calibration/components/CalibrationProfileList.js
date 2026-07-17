import Link from "next/link";
import {
  FiArrowRight,
  FiCamera,
} from "react-icons/fi";

import SubsectionHeader from "@/components/headers/SubsectionHeader";
import InnerPanel from "@/components/panels/InnerPanel";
import { StatusPill } from "@/components/panels/Panel";

import {
  calibrationDateTime,
  calibrationStatus,
  formatCalibrationNumber,
} from "../lib/calibrationUtils";

function errorLabel(value) {
  const formatted = formatCalibrationNumber(value);
  return formatted === "—" ? formatted : `${formatted} px`;
}

export default function CalibrationProfileList({ profiles }) {
  return (
    <div className="grid gap-3">
      <SubsectionHeader
        title="校正檔案"
        description="有效狀態只代表資料完整且相機與來源指紋未變更，不代表達成未經定義的品質門檻。"
      />

      {profiles.length ? (
        <div className="grid gap-3 min-[900px]:grid-cols-2">
          {profiles.map((profile) => {
            const status = calibrationStatus(profile.status);
            return (
              <InnerPanel
                as="article"
                className="content-start"
                key={profile.calibration_id}
              >
                <div className="grid min-w-0 grid-cols-[minmax(0,1fr)_auto] items-start gap-3">
                  <div className="min-w-0">
                    <div className="flex min-w-0 items-center gap-2">
                      <FiCamera
                        className="size-4 shrink-0 text-emerald-200"
                        aria-hidden="true"
                      />
                      <h3 className="m-0 truncate text-sm font-black text-white">
                        {profile.calibration_id}
                      </h3>
                    </div>
                    <p className="mt-1 text-xs font-semibold text-neutral-400">
                      建立：{calibrationDateTime(profile.created_at)}
                    </p>
                  </div>
                  <StatusPill tone={status.tone}>{status.label}</StatusPill>
                </div>

                <dl className="grid grid-cols-2 gap-3 rounded-xl border border-white/10 bg-black/10 p-3 text-xs">
                  <div className="min-w-0">
                    <dt className="font-black text-neutral-500">解析度</dt>
                    <dd className="mt-1 m-0 font-bold text-neutral-200">
                      {profile.image_width && profile.image_height
                        ? `${profile.image_width} × ${profile.image_height}`
                        : "尚未求解"
                      }
                    </dd>
                  </div>
                  <div className="min-w-0">
                    <dt className="font-black text-neutral-500">雙目誤差</dt>
                    <dd className="mt-1 m-0 font-bold text-neutral-200">
                      {errorLabel(profile.stereo_mean_reprojection_error)}
                    </dd>
                  </div>
                  <div className="min-w-0">
                    <dt className="font-black text-neutral-500">俯視角誤差</dt>
                    <dd className="mt-1 m-0 font-bold text-neutral-200">
                      {errorLabel(profile.top_mean_reprojection_error)}
                    </dd>
                  </div>
                  <div className="min-w-0">
                    <dt className="font-black text-neutral-500">側視角誤差</dt>
                    <dd className="mt-1 m-0 font-bold text-neutral-200">
                      {errorLabel(profile.side_mean_reprojection_error)}
                    </dd>
                  </div>
                </dl>

                {profile.potentially_invalid_reasons?.length ? (
                  <ul className="m-0 grid gap-1 rounded-xl border border-amber-200/25 bg-amber-500/10 p-3 pl-7 text-xs font-semibold text-amber-200">
                    {profile.potentially_invalid_reasons.map((reason) => (
                      <li key={reason}>{reason}</li>
                    ))}
                  </ul>
                ) : null}

                <div className="flex justify-end">
                  <Link
                    className="inline-flex min-h-10 min-w-0 items-center justify-center gap-2 rounded-xl border border-white/15 bg-white/[0.07] px-4 py-2 text-sm font-extrabold text-neutral-200 transition-[background-color,border-color,color,opacity] duration-150 hover:border-white/25 hover:bg-white/[0.13] focus-visible:outline-2 focus-visible:outline-emerald-300"
                    href={`/analysis/calibration/${encodeURIComponent(profile.calibration_id)}`}
                  >
                    <FiArrowRight
                      className="size-4 shrink-0"
                      aria-hidden="true"
                    />
                    查看工作流
                  </Link>
                </div>
              </InnerPanel>
            );
          })}
        </div>
      ) : (
        <div className="grid min-h-28 place-items-center rounded-xl border border-dashed border-white/10 bg-black/10 p-4 text-center text-sm font-semibold text-neutral-400">
          尚無校正檔案，請在下方選擇影像並填入實測規格。
        </div>
      )}
    </div>
  );
}

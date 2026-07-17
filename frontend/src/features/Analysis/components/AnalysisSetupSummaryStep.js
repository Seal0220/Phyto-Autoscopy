import StatusCard from "@/components/cards/StatusCard";
import InnerPanel from "@/components/panels/InnerPanel";
import { StatusPill } from "@/components/panels/Panel";
import SubsectionHeader from "@/components/headers/SubsectionHeader";
import { formatDateTime } from "@/lib/formatUtils";

import { ANALYSIS_METHODS } from "../analysisConfig";
import {
  analysisFrameCount,
  analysisStatusMeta,
} from "../lib/analysisUtils";

function roiLabel(roi) {
  return `${roi.x}, ${roi.y}, ${roi.width} × ${roi.height} px`;
}

export default function AnalysisSetupSummaryStep({
  setup,
  source,
  calibration,
  createdRun,
}) {
  const status = createdRun
    ? analysisStatusMeta(createdRun.status)
    : null;
  const method = ANALYSIS_METHODS[setup.method];

  return (
    <section
      className="grid gap-4"
      aria-labelledby="analysis-summary-step-title"
    >
      <SubsectionHeader
        titleId="analysis-summary-step-title"
        title="確認並建立分析"
        description="建立後依序驗證輸入與影格配對，再明確開始背景分析工作。"
      >
        {status ? (
          <StatusPill tone={status.tone}>{status.label}</StatusPill>
        ) : null}
      </SubsectionHeader>

      {createdRun ? (
        <div className="grid gap-3 min-[720px]:grid-cols-3">
          <StatusCard
            title="分析 ID"
            content={createdRun.analysis_id}
            note="已建立"
            className="[&>div:first-of-type]:break-all [&>div:first-of-type]:text-base"
          />
          <StatusCard
            title="分析狀態"
            content={status.label}
            note="目前狀態"
          />
          <StatusCard
            title="處理進度"
            content={`${Math.round(createdRun.progress * 100)}%`}
            note={createdRun.total_frames > 0
              ? `${createdRun.current_frame} / ${createdRun.total_frames} 影格`
              : "尚未開始"
            }
          />
        </div>
      ) : null}

      <InnerPanel>
        <dl className="grid min-w-0 gap-4 text-sm min-[520px]:grid-cols-2 min-[900px]:grid-cols-3">
          <div className="min-w-0">
            <dt className="text-xs font-black text-neutral-500">捕捉紀錄</dt>
            <dd className="mt-1 m-0 break-all font-bold text-neutral-100">
              {source?.record_id || setup.recordId || "—"}
            </dd>
          </div>
          <div className="min-w-0">
            <dt className="text-xs font-black text-neutral-500">相機校正</dt>
            <dd className="mt-1 m-0 break-all font-bold text-neutral-100">
              {calibration?.calibration_id || setup.calibrationId || "—"}
            </dd>
          </div>
          <div>
            <dt className="text-xs font-black text-neutral-500">校正建立時間</dt>
            <dd className="mt-1 m-0 font-bold text-neutral-100">
              {formatDateTime(calibration?.created_at)}
            </dd>
          </div>
          <div className="min-w-0">
            <dt className="text-xs font-black text-neutral-500">分析方法</dt>
            <dd className="mt-1 m-0 break-all font-bold text-neutral-100">
              {method.label}
            </dd>
          </div>
          <div>
            <dt className="text-xs font-black text-neutral-500">相機來源</dt>
            <dd className="mt-1 m-0 font-bold text-neutral-100">
              {Object.entries(setup.cameraSources)
                .filter(([, cameraSource]) => cameraSource.enabled)
                .map(([cameraId]) => cameraId)
                .join("、")}
            </dd>
          </div>
          <div>
            <dt className="text-xs font-black text-neutral-500">分析影格</dt>
            <dd className="mt-1 m-0 font-bold text-neutral-100">
              {setup.startFrame}–{setup.endFrame}（{analysisFrameCount(setup)} 組）
            </dd>
          </div>
          <div>
            <dt className="text-xs font-black text-neutral-500">人工影格偏移</dt>
            <dd className="mt-1 m-0 font-bold text-neutral-100">
              {setup.manualFrameOffset} 影格
            </dd>
          </div>
          <div>
            <dt className="text-xs font-black text-neutral-500">俯視 ROI</dt>
            <dd className="mt-1 m-0 font-bold text-neutral-100">
              {roiLabel(setup.topRoi)}
            </dd>
          </div>
          <div>
            <dt className="text-xs font-black text-neutral-500">側視 ROI</dt>
            <dd className="mt-1 m-0 font-bold text-neutral-100">
              {roiLabel(setup.sideRoi)}
            </dd>
          </div>
          <div>
            <dt className="text-xs font-black text-neutral-500">人工修正</dt>
            <dd className="mt-1 m-0 font-bold text-neutral-100">
              {setup.manualReviewRequired ? "完成自動偵測後等待人工修正" : "不等待人工修正"}
            </dd>
          </div>
          <div className="min-w-0 min-[520px]:col-span-2">
            <dt className="text-xs font-black text-neutral-500">輸出位置</dt>
            <dd className="mt-1 m-0 break-all font-bold text-neutral-100">
              {createdRun?.output_path
                || "尚未建立；由後端依分析儲存設定產生"
              }
            </dd>
          </div>
        </dl>
      </InnerPanel>

      <p className="m-0 text-xs font-semibold leading-5 text-neutral-400">
        原始捕捉資料保持唯讀；所有自動偵測、人工修正、三維座標與錯誤紀錄會寫入獨立分析目錄。
      </p>
    </section>
  );
}

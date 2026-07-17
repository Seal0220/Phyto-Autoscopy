import {
  FiCheckCircle,
  FiCrosshair,
  FiGrid,
  FiLayers,
  FiRotateCw,
} from "react-icons/fi";

import Button from "@/components/buttons/Button";
import SubsectionHeader from "@/components/headers/SubsectionHeader";
import InnerPanel from "@/components/panels/InnerPanel";
import { StatusPill } from "@/components/panels/Panel";

import { CALIBRATION_WORKFLOW_STEPS } from "../calibrationConfig";
import {
  calibrationWorkflowAvailability,
  calibrationWorkflowStepState,
} from "../lib/calibrationUtils";

const STEP_ICONS = {
  corners: FiCrosshair,
  intrinsics: FiGrid,
  stereo: FiLayers,
  rotating: FiRotateCw,
  validate: FiCheckCircle,
};

export default function CalibrationWorkflowActions({
  profile,
  pending,
  requiresRefresh,
  onRun,
}) {
  const availability = calibrationWorkflowAvailability(profile);

  return (
    <InnerPanel
      as="section"
      aria-labelledby="calibration-workflow-title"
    >
      <SubsectionHeader
        titleId="calibration-workflow-title"
        title="校正工作流"
        description="依序執行角點偵測、三相機內參、俯視加側視校正、選用的環繞幾何及完整性驗證；失敗後可清除錯誤並重試。"
      />
      <ol className="m-0 grid list-none gap-3 p-0 min-[900px]:grid-cols-5">
        {CALIBRATION_WORKFLOW_STEPS.map((step, index) => {
          const Icon = STEP_ICONS[step.key];
          const state = calibrationWorkflowStepState(
            profile,
            step.key,
          );
          const complete = ["已完成", "已通過"].includes(state);
          return (
            <li
              className="grid content-start gap-3 rounded-xl border border-white/10 bg-black/10 p-3"
              key={step.key}
            >
              <div className="flex items-start justify-between gap-2">
                <span className="grid size-8 shrink-0 place-items-center rounded-xl border border-emerald-200/20 bg-emerald-400/10 text-emerald-200">
                  <Icon
                    className="size-4"
                    aria-hidden="true"
                  />
                </span>
                <StatusPill tone={complete ? "success" : "neutral"}>
                  {state}
                </StatusPill>
              </div>
              <div className="min-w-0">
                <p className="m-0 text-[11px] font-black text-neutral-500">
                  步驟 {index + 1}
                </p>
                <h4 className="mt-1 m-0 text-sm font-black text-white">
                  {step.label}
                </h4>
              </div>
              <Button
                className="mt-auto w-full"
                disabled={
                  Boolean(pending)
                  || requiresRefresh
                  || !availability[step.key]
                }
                onClick={() => onRun(step.key)}
              >
                <Icon
                  className="size-4 shrink-0"
                  aria-hidden="true"
                />
                {pending === step.key ? step.pendingLabel : (
                  complete ? "重新執行" : step.label
                )}
              </Button>
            </li>
          );
        })}
      </ol>
      <p className="m-0 text-xs font-semibold text-neutral-400">
        驗證只檢查資料完整性、有限數值、矩陣／ROI 合法性與相機／來源是否變更；本系統不設定論文未定義的重投影誤差通過門檻，也不提供品質保證。
      </p>
    </InnerPanel>
  );
}

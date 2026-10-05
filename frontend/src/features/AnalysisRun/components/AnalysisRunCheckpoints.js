import DisclosurePanel from "@/components/panels/DisclosurePanel";

import { ANALYSIS_STAGE_LABELS } from "../../Analysis/analysisConfig";
import { formatAnalysisTimestamp } from "../lib/analysisRunUtils";

export default function AnalysisRunCheckpoints({
  checkpoints,
  status,
}) {
  const steps = Array.isArray(checkpoints?.recent_steps) ? checkpoints.recent_steps : [];
  let description = `已保存 ${checkpoints?.completed_steps || 0} 個步驟；展開查看最近完成項目。`;
  if (status === "pausing") {
    description = "正在等待目前步驟完成並保存；模型訓練會保存權重與最佳化器狀態。";
  } else if (status === "paused") {
    description = "可恢復分析，重用已完成影像與各輪結果，從保存的訓練步數繼續。";
  }

  return (
    <DisclosurePanel
      title="已保存步驟"
      description={description}
    >
      {steps.length ? (
        <ol className="m-0 grid list-none gap-2 p-0">
          {steps.map((step) => (
            <li
              key={`${step.stage}:${step.item}`}
              className="grid min-w-0 gap-1 border-b border-white/10 pb-2 text-xs last:border-0"
            >
              <span className="font-semibold text-neutral-200">
                {ANALYSIS_STAGE_LABELS[step.stage] || "處理步驟"}
                {step.backend ? ` · ${step.backend === "cpu" ? "CPU" : "GPU"}` : ""}
              </span>
              <span className="break-all text-neutral-400">{step.item}</span>
              <span className="text-neutral-500">{formatAnalysisTimestamp(step.updated_at)}</span>
            </li>
          ))}
        </ol>
      ) : (
        <p className="m-0 text-sm text-neutral-400">尚無完成的步驟。</p>
      )}
    </DisclosurePanel>
  );
}

import InnerPanel from "@/components/panels/InnerPanel";
import SubsectionHeader from "@/components/headers/SubsectionHeader";

import {
  analysisInputCount,
  formatAnalysisTimestamp,
  framePairCounts,
  truncateCommit,
} from "../lib/analysisRunUtils";

function MetadataItem({
  label,
  value,
}) {
  return (
    <div className="min-w-0">
      <dt className="text-xs font-black text-neutral-400">{label}</dt>
      <dd className="mt-1 min-w-0 wrap-break-word text-sm font-bold text-neutral-100">
        {value || "—"}
      </dd>
    </div>
  );
}

export default function AnalysisRunMetadata({
  framePairs,
  run,
}) {
  const pairCounts = framePairCounts(framePairs);

  return (
    <div className="grid gap-4 min-[900px]:grid-cols-2">
      <InnerPanel>
        <SubsectionHeader
          title="輸入與方法"
          description="分析紀錄建立時固化的輸入與重現資訊。"
        />
        <dl className="grid gap-4 min-[520px]:grid-cols-2">
          <MetadataItem
            label="分析 ID"
            value={run.analysis_id}
          />
          <MetadataItem
            label="捕捉紀錄 ID"
            value={run.record_id}
          />
          <MetadataItem
            label="相機校正 ID"
            value={run.calibration_id}
          />
          <MetadataItem
            label="輸入影像"
            value={`${analysisInputCount(run)} 張`}
          />
          <MetadataItem
            label="方法"
            value={run.method_name}
          />
          <MetadataItem
            label="方法版本"
            value={run.method_version}
          />
          <MetadataItem
            label="Git 提交"
            value={truncateCommit(run.git_commit)}
          />
          <MetadataItem
            label="建立者"
            value={run.created_by}
          />
        </dl>
      </InnerPanel>

      <InnerPanel>
        <SubsectionHeader
          title="配對與輸出"
          description="原始捕捉紀錄保持唯讀，分析檔案只寫入輸出目錄。"
        />
        <dl className="grid gap-4 min-[520px]:grid-cols-2">
          <MetadataItem
            label="一般配對"
            value={`${pairCounts.paired} 組`}
          />
          <MetadataItem
            label="人工偏移配對"
            value={`${pairCounts.manuallyAligned} 組`}
          />
          <MetadataItem
            label="未解決配對"
            value={`${pairCounts.unresolved} 組`}
          />
          <MetadataItem
            label="人工檢查"
            value={run.manual_review_completed ? "已完成" : "尚未完成"}
          />
          <MetadataItem
            label="建立時間"
            value={formatAnalysisTimestamp(run.created_at)}
          />
          <MetadataItem
            label="最後更新"
            value={formatAnalysisTimestamp(run.updated_at)}
          />
          <div className="min-w-0 min-[520px]:col-span-2">
            <MetadataItem
              label="輸出目錄"
              value={run.output_path}
            />
          </div>
        </dl>
      </InnerPanel>
    </div>
  );
}

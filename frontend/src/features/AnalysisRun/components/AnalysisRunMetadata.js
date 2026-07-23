import InformationGrid from "@/components/data/InformationGrid";
import SubsectionHeader from "@/components/headers/SubsectionHeader";
import InnerPanel from "@/components/panels/InnerPanel";
import {
  ANALYSIS_CAMERA_LABELS,
  ANALYSIS_METHODS,
} from "@/features/Analysis/analysisConfig";

import {
  analysisInputCount,
  formatAnalysisTimestamp,
  truncateCommit,
} from "../lib/analysisRunUtils";

function enabledCameraLabel(run) {
  const sources = run?.parameters?.camera_sources;
  if (!sources || typeof sources !== "object") return "尚無資料";

  const labels = Object.entries(sources)
    .filter(([, source]) => source?.enabled)
    .map(([cameraId]) => ANALYSIS_CAMERA_LABELS[cameraId] || cameraId);

  return labels.length ? labels.join("、") : "尚無資料";
}

function analysisMetadata(
  run,
  formalData,
) {
  const rounds = formalData?.rounds || [];
  const models = formalData?.models || [];
  const landmarks = formalData?.landmarks || [];
  const trajectory = formalData?.trajectory || [];
  const modeIds = Array.isArray(run?.parameters?.mode_ids)
    ? run.parameters.mode_ids
    : [];

  return {
    inputItems: [
      {
        label: "分析 ID",
        value: run.analysis_id,
        truncate: true,
      },
      {
        label: "捕捉紀錄 ID",
        value: run.record_id || "尚無資料",
        truncate: true,
      },
      {
        label: "分析方法",
        value: ANALYSIS_METHODS[run.method_name]?.label || "尚無資料",
      },
      {
        label: "方法版本",
        value: run.method_version || "尚無資料",
      },
      {
        label: "選取模式",
        value: modeIds.length ? modeIds.join("、") : "尚無資料",
        truncate: true,
      },
      {
        label: "啟用相機",
        value: enabledCameraLabel(run),
      },
      {
        label: "輸入影像",
        value: `${analysisInputCount(run)} 張`,
      },
      {
        label: "座標空間",
        value: run.parameters?.coordinate_space === "undistorted"
          ? "去畸變影像座標"
          : "尚無資料",
      },
    ],
    outputItems: [
      {
        label: "Analysis Round",
        value: `${run.round_count || rounds.length} 輪`,
      },
      {
        label: "完成 Round",
        value: `${run.completed_round_count || 0} 輪`,
      },
      {
        label: "異常 Round",
        value: `${run.failed_round_count || 0} 輪`,
      },
      {
        label: "完成模型",
        value: `${models.filter((item) => item.status === "completed").length} 個`,
      },
      {
        label: "有效尖端標記",
        value: `${landmarks.filter((item) => item.valid).length} 個`,
      },
      {
        label: "尖端標記軌跡",
        value: `${trajectory.filter((item) => item.valid).length} 個有效點`,
      },
      {
        label: "模型後端",
        value: run.reconstruction_backend || "不建立模型",
      },
      {
        label: "人工確認",
        value: run.manual_review_completed ? "已完成" : "尚未完成",
      },
    ],
  };
}

export default function AnalysisRunMetadata({
  formalData,
  run,
}) {
  const metadata = analysisMetadata(run, formalData);

  return (
    <div className="grid gap-4 min-[900px]:grid-cols-2">
      <InnerPanel>
        <SubsectionHeader
          title="輸入與方法"
          description="分析建立時固化的輸入、相機與重現資訊。"
        />
        <InformationGrid
          items={metadata.inputItems}
          rows={4}
          minimumColumnWidth
          scroll
        />
      </InnerPanel>

      <InnerPanel>
        <SubsectionHeader
          title="Round 與輸出"
          description="原始捕捉紀錄保持唯讀，衍生資料只寫入分析輸出目錄。"
        />
        <InformationGrid
          items={metadata.outputItems}
          rows={4}
          minimumColumnWidth
          scroll
        />
        <InformationGrid
          items={[
            {
              label: "建立時間",
              value: formatAnalysisTimestamp(run.created_at),
            },
            {
              label: "最後更新",
              value: formatAnalysisTimestamp(run.updated_at),
            },
            {
              label: "Git 提交",
              value: truncateCommit(run.git_commit),
            },
            {
              label: "輸出目錄",
              value: run.output_path || "尚無資料",
              truncate: true,
            },
          ]}
          rows={2}
          minimumColumnWidth
          scroll
        />
      </InnerPanel>
    </div>
  );
}

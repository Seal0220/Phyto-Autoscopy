import FullscreenImage from "@/components/media/FullscreenImage";
import InformationGrid from "@/components/data/InformationGrid";
import SubsectionHeader from "@/components/headers/SubsectionHeader";
import InnerPanel from "@/components/panels/InnerPanel";
import { StatusPill } from "@/components/panels/Panel";
import {
  ANALYSIS_MODEL_STATUS_META,
  RECONSTRUCTION_BACKEND_LABELS,
} from "@/features/Analysis/analysisConfig";

function artifactUrl(
  analysisId,
  artifactPath,
) {
  const encodedPath = String(artifactPath)
    .split(/[\\/]/u)
    .filter(Boolean)
    .map((segment) => encodeURIComponent(segment))
    .join("/");

  return (
    `/api/analysis/${encodeURIComponent(analysisId)}`
    + `/artifacts/${encodedPath}`
  );
}

function outputItem(
  label,
  path,
) {
  return {
    label,
    value: path ? "已產生" : "未輸出",
    tone: path ? "success" : "neutral",
  };
}

function modelStatus(model) {
  return ANALYSIS_MODEL_STATUS_META[model.status] || {
    label: "尚無模型",
    tone: "neutral",
  };
}

function displayNumber(
  value,
  suffix = "",
  digits = 0,
) {
  if (value === null || value === undefined || value === "") {
    return "尚無資料";
  }
  const number = Number(value);

  return Number.isFinite(number)
    ? `${number.toFixed(digits)}${suffix}`
    : "尚無資料";
}

function displayPercentage(value) {
  if (value === null || value === undefined || value === "") {
    return "尚無資料";
  }
  return displayNumber(
    Number(value) * 100,
    "%",
    1,
  );
}

export default function TrajectoryViewerModelOutputs({
  analysisId,
  models = [],
}) {
  return (
    <InnerPanel>
      <SubsectionHeader
        title="每輪模型輸出"
        description="完整場景、植物與背景輸出會依建立分析時的輸出設定分別保存。"
      />

      {models.length ? (
        <div className="grid max-h-[42rem] gap-3 overflow-y-auto pr-1 min-[900px]:grid-cols-2">
          {models.map((model) => {
            const status = modelStatus(model);
            const previewPath = model.preview_paths?.[0] || "";

            return (
              <article
                className="grid min-w-0 content-start gap-3 rounded-xl border border-white/15 bg-black/15 p-3"
                key={model.round_key}
              >
                <div className="flex min-w-0 items-center justify-between gap-3">
                  <h4 className="m-0 min-w-0 truncate text-sm font-black text-white">
                    {model.round_key}
                  </h4>
                  <StatusPill tone={status.tone}>
                    {status.label}
                  </StatusPill>
                </div>

                {previewPath ? (
                  <div className="relative aspect-video min-w-0 overflow-hidden rounded-xl border border-white/15 bg-black">
                    <img
                      className="size-full object-contain"
                      src={artifactUrl(analysisId, previewPath)}
                      alt={`${model.round_key} 模型預覽`}
                    />
                    <FullscreenImage
                      src={artifactUrl(analysisId, previewPath)}
                      alt={`${model.round_key} 模型預覽`}
                      label={`${model.round_key} 模型預覽`}
                    />
                  </div>
                ) : null}

                <InformationGrid
                  items={[
                    outputItem("完整 Gaussian", model.model_path),
                    outputItem("植物 Gaussian", model.plant_model_path),
                    outputItem("背景 Gaussian", model.background_model_path),
                    outputItem("完整點雲", model.point_cloud_path),
                    outputItem("植物點雲", model.plant_point_cloud_path),
                    outputItem(
                      "背景點雲",
                      model.background_point_cloud_path,
                    ),
                    outputItem("植物骨架", model.skeleton_path),
                    {
                      label: "模型預覽",
                      value: model.preview_paths?.length
                        ? `${model.preview_paths.length} 張`
                        : "未輸出",
                      tone: model.preview_paths?.length
                        ? "success"
                        : "neutral",
                    },
                  ]}
                  rows={4}
                />

                <InformationGrid
                  items={[
                    {
                      label: "來源視角",
                      value: `${model.source_view_ids?.length || 0} 張`,
                    },
                    {
                      label: "模型後端",
                      value: RECONSTRUCTION_BACKEND_LABELS[
                        model.backend
                      ] || "尚無資料",
                    },
                    {
                      label: "後端版本",
                      value: model.backend_version || "尚無資料",
                    },
                    {
                      label: "後端提交",
                      value: model.repository_commit
                        ? model.repository_commit.slice(0, 12)
                        : "尚無資料",
                    },
                    {
                      label: "授權",
                      value: model.license || "尚無資料",
                    },
                    {
                      label: "Gaussian 數量",
                      value: displayNumber(model.gaussian_count),
                    },
                    {
                      label: "初始點數",
                      value: displayNumber(model.point_count),
                    },
                    {
                      label: "訓練迭代",
                      value: displayNumber(model.training_iterations),
                    },
                    {
                      label: "訓練時間",
                      value: displayNumber(
                        model.training_duration_seconds,
                        " 秒",
                        1,
                      ),
                    },
                    {
                      label: "植物占比",
                      value: displayPercentage(
                        model.model_quality
                          ?.plant_isolation
                          ?.plant_ratio
                        ?? model.model_quality
                          ?.plant_gaussian_export
                          ?.plant_ratio,
                      ),
                    },
                  ]}
                  rows={5}
                />

                {model.failure_reason ? (
                  <p className="m-0 text-xs font-semibold text-rose-200">
                    {model.failure_reason}
                  </p>
                ) : null}
              </article>
            );
          })}
        </div>
      ) : (
        <div className="grid min-h-24 place-items-center rounded-xl border border-white/15 bg-black/15 p-4 text-sm font-semibold text-neutral-400">
          此分析方法沒有建立每輪三維模型。
        </div>
      )}
    </InnerPanel>
  );
}

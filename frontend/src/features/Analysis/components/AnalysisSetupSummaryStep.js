import InformationGrid from "@/components/data/InformationGrid";
import StatusCard from "@/components/cards/StatusCard";
import SubsectionHeader from "@/components/headers/SubsectionHeader";
import DisclosurePanel from "@/components/panels/DisclosurePanel";
import InnerPanel from "@/components/panels/InnerPanel";
import { StatusPill } from "@/components/panels/Panel";

import {
  ANALYSIS_CAMERA_LABELS,
  ANALYSIS_METHODS,
  RECONSTRUCTION_BACKEND_LABELS,
  RECONSTRUCTION_QUALITY_LABELS,
} from "../analysisConfig";
import { analysisStatusMeta } from "../lib/analysisUtils";

function displayNumber(
  value,
  suffix = "",
) {
  if (value === null || value === undefined || value === "") {
    return "尚無資料";
  }
  const number = Number(value);
  return Number.isFinite(number)
    ? `${number}${suffix}`
    : "尚無資料";
}

export default function AnalysisSetupSummaryStep({
  setup,
  source,
  createdRun,
}) {
  const status = createdRun
    ? analysisStatusMeta(createdRun.status)
    : null;
  const method = ANALYSIS_METHODS[setup.method];
  const buildsRoundModels = setup.method === "rotating";
  const preview = setup.sourcePreview || {};
  const intrinsics = preview.intrinsics_readiness || {};
  const pose = preview.pose_readiness || {};
  const backend = preview.backend_readiness || {};
  const selectedModes = setup.availableModes.filter(
    (mode) => setup.selectedModeIds.includes(mode.id),
  );
  const enabledCameraIds = Object.entries(setup.cameraSources)
    .filter(([, cameraSource]) => cameraSource.enabled)
    .map(([cameraId]) => cameraId);

  return (
    <section
      className="grid gap-4"
      aria-labelledby="analysis-summary-step-title"
    >
      <SubsectionHeader
        titleId="analysis-summary-step-title"
        title="確認並建立"
        description={buildsRoundModels
          ? "建立前確認 Round、相機內參、實測雙鏡頭基線、模型後端與預期輸出。"
          : "建立前確認 Round、相機內參、實測雙鏡頭基線與尖端標記輸出。"
        }
      >
        {status ? (
          <StatusPill tone={status.tone}>
            {status.label}
          </StatusPill>
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
            note={createdRun.round_count > 0
              ? `${createdRun.completed_round_count || 0} / ${createdRun.round_count} 輪`
              : "尚未開始"
            }
          />
        </div>
      ) : null}

      <InnerPanel>
        <SubsectionHeader
          title="紀錄與模式"
          description="所有通過驗證的輪次都會納入分析。"
          titleMode={1}
        />
        <InformationGrid
          items={[
            {
              label: "紀錄 ID",
              value: source?.record_id || setup.recordId || "尚無資料",
              truncate: true,
            },
            {
              label: "選取模式",
              value: `${selectedModes.length} 種`,
            },
            {
              label: "輪次數量",
              value: `${preview.round_count || 0} 輪`,
            },
            {
              label: "有效輪次",
              value: `${preview.ready_round_count || 0} 輪`,
              tone: preview.ready ? "success" : "warning",
            },
            {
              label: "不完整輪次",
              value: `${preview.incomplete_round_count || 0} 輪`,
              tone: preview.incomplete_round_count > 0
                ? "warning"
                : "success",
            },
            {
              label: "總影像數",
              value: `${preview.total_view_count || 0} 張`,
            },
          ]}
          columns={3}
          scroll
        />
        <p className="m-0 break-all text-xs font-semibold text-neutral-400">
          根目錄：{setup.recordPath || "尚無資料"}
        </p>
      </InnerPanel>

      <InnerPanel>
        <SubsectionHeader
          title="相機與內部參數"
          description="建立分析時固化各實體相機的內參；之後更新校正不會改寫本次分析。"
          titleMode={1}
        />
        <div className="grid gap-3 min-[720px]:grid-cols-3">
          {enabledCameraIds.map((cameraId) => {
            const item = intrinsics[cameraId] || {};

            return (
              <InnerPanel
                className="gap-3 p-3"
                key={cameraId}
                mode="dark"
              >
                <div className="flex items-center justify-between gap-3">
                  <span className="text-sm font-black text-white">
                    {ANALYSIS_CAMERA_LABELS[cameraId]}
                  </span>
                  <StatusPill tone={item.ready ? "success" : "offline"}>
                    {item.ready ? "內參有效" : "內參未就緒"}
                  </StatusPill>
                </div>
                <InformationGrid
                  items={[
                    {
                      label: "模型",
                      value: item.camera_model || "尚無資料",
                    },
                    {
                      label: "解析度",
                      value: item.width && item.height
                        ? `${item.width} × ${item.height}`
                        : "尚無資料",
                    },
                    {
                      label: "重投影誤差",
                      value: displayNumber(
                        item.reprojection_error_px,
                        " px",
                      ),
                    },
                  ]}
                  border="none"
                  rows={3}
                />
              </InnerPanel>
            );
          })}
        </div>
      </InnerPanel>

      <div
        className={`grid gap-4 ${
          buildsRoundModels ? "min-[900px]:grid-cols-2" : ""
        }`}
      >
        <InnerPanel>
          <SubsectionHeader
            title="無標記世界基準"
            description="俯視鏡頭正下方的平台點為世界原點；影像特徵決定相對姿態，實測距離固定毫米尺度。"
            titleMode={1}
          />
          <InformationGrid
            items={[
              {
                label: "內參狀態",
                value: pose.intrinsics_ready ? "有效" : "未就緒",
                tone: pose.intrinsics_ready ? "success" : "error",
              },
              {
                label: "尺度來源",
                value: "實測雙鏡頭基線",
              },
              {
                label: "基線",
                value: displayNumber(setup.parameters.baselineMm, " mm"),
              },
              {
                label: "俯視鏡頭高度",
                value: displayNumber(setup.parameters.topHeightMm, " mm"),
              },
              {
                label: "雙鏡頭最少內點",
                value: displayNumber(setup.parameters.minimumStereoInliers, " 點"),
              },
              {
                label: "極線誤差上限",
                value: displayNumber(setup.parameters.maximumEpipolarErrorPx, " px"),
              },
              {
                label: "雙鏡頭重投影上限",
                value: displayNumber(setup.parameters.maximumStereoReprojectionErrorPx, " px"),
              },
              {
                label: "姿態估算",
                value: "執行分析時進行",
              },
              {
                label: "世界單位",
                value: "mm",
              },
            ]}
            rows={4}
          />
        </InnerPanel>

        {buildsRoundModels ? (
          <InnerPanel>
            <SubsectionHeader
              title="模型後端"
              description="建立前會再次檢查 CUDA、PyCOLMAP、Open3D 與模型後端。"
              titleMode={1}
            />
            <InformationGrid
              items={[
                {
                  label: "後端",
                  value: RECONSTRUCTION_BACKEND_LABELS[
                    setup.parameters.reconstructionBackend
                  ] || "尚無資料",
                },
                {
                  label: "狀態",
                  value: backend.backend === setup.parameters.reconstructionBackend
                    ? (backend.available ? "可用" : "不可用")
                    : "建立時檢查",
                  tone: backend.backend === setup.parameters.reconstructionBackend
                    ? (backend.available ? "success" : "error")
                    : "neutral",
                },
                {
                  label: "GPU",
                  value: backend.environment?.gpu_name || "尚無資料",
                },
                {
                  label: "PyTorch",
                  value: backend.environment?.pytorch_version || "未安裝",
                },
                {
                  label: "CUDA",
                  value: backend.environment?.cuda_runtime_version || "不可用",
                },
                {
                  label: "品質模式",
                  value: RECONSTRUCTION_QUALITY_LABELS[
                    setup.parameters.qualityPreset
                  ] || "尚無資料",
                },
                {
                  label: "訓練步數",
                  value: displayNumber(setup.parameters.trainingIterations, " 步"),
                },
                ...(setup.parameters.reconstructionBackend === "gsplat_3dgs"
                  ? [{
                    label: "影像縮小倍率",
                    value: `${setup.parameters.imageFactor} 倍`,
                  }]
                  : []),
              ]}
              rows={3}
            />
          </InnerPanel>
        ) : null}
      </div>

      <DisclosurePanel
        title="方法與輸出"
        description="原始 Record 保持唯讀，所有衍生資料寫入獨立分析目錄。"
      >
        <InformationGrid
          items={[
            {
              label: "分析方法",
              value: method.label,
            },
            ...(buildsRoundModels
              ? [
                {
                  label: "姿態精修",
                  value: setup.parameters.useBundleAdjustment
                    ? "啟用"
                    : "停用",
                },
                {
                  label: "完整 Gaussian",
                  value: (
                    setup.parameters.saveGaussianModel
                    && setup.parameters.preserveSceneModel
                  )
                    ? "建立"
                    : "不建立",
                },
                {
                  label: "植物 Gaussian",
                  value: (
                    setup.parameters.saveGaussianModel
                    && setup.parameters.exportPlantModel
                  )
                    ? "建立"
                    : "不建立",
                },
                {
                  label: "背景 Gaussian",
                  value: (
                    setup.parameters.saveGaussianModel
                    && setup.parameters.saveBackgroundModel
                  )
                    ? "建立"
                    : "不建立",
                },
                {
                  label: "完整點雲",
                  value: setup.parameters.exportScenePointCloud
                    ? "建立"
                    : "不建立",
                },
                {
                  label: "植物點雲",
                  value: setup.parameters.exportPlantPointCloud
                    ? "建立"
                    : "不建立",
                },
                {
                  label: "背景點雲",
                  value: setup.parameters.saveBackgroundModel
                    ? "建立"
                    : "不建立",
                },
                {
                  label: "植物骨架",
                  value: setup.parameters.exportSkeleton
                    ? "建立"
                    : "不建立",
                },
              ]
              : []
            ),
            {
              label: "尖端標記",
              value: setup.parameters.exportTipMarkers ? "建立" : "不建立",
            },
            {
              label: "二維尖端候選",
              value: setup.parameters.exportAll2dCandidates
                ? "輸出全部"
                : "只輸出選取結果",
            },
            {
              label: "重投影疊圖",
              value: setup.parameters.saveReprojectionOverlays
                ? "建立"
                : "不建立",
            },
            {
              label: "尖端標記軌跡 CSV",
              value: setup.parameters.exportTrajectoryCsv ? "建立" : "不建立",
            },
            {
              label: "人工確認",
              value: setup.manualReviewRequired ? "需要" : "不等待",
            },
          ]}
          columns={4}
          scroll
        />
        <p className="m-0 text-xs font-semibold leading-5 text-neutral-400">
          輸出位置：{createdRun?.output_path || "建立後由後端產生"}
        </p>
      </DisclosurePanel>
    </section>
  );
}

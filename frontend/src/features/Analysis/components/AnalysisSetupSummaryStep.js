import InformationGrid from "@/components/data/InformationGrid";
import StatusCard from "@/components/cards/StatusCard";
import SubsectionHeader from "@/components/headers/SubsectionHeader";
import InnerPanel from "@/components/panels/InnerPanel";
import { StatusPill } from "@/components/panels/Panel";

import {
  ANALYSIS_CAMERA_LABELS,
  ANALYSIS_METHODS,
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
  const preview = setup.sourcePreview || {};
  const intrinsics = preview.intrinsics_readiness || {};
  const aruco = preview.aruco_readiness || {};
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
        description="建立前確認 Round、相機內參、ArUco 基準、模型後端與預期輸出。"
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
          title="Record 與模式"
          description="所有通過驗證的 Round 都會納入，不使用全域影格範圍。"
          titleMode={1}
        />
        <InformationGrid
          items={[
            {
              label: "Record ID",
              value: source?.record_id || setup.recordId || "尚無資料",
              truncate: true,
            },
            {
              label: "選取模式",
              value: `${selectedModes.length} 種`,
            },
            {
              label: "Round 數量",
              value: `${preview.round_count || 0} 輪`,
            },
            {
              label: "有效 Round",
              value: `${preview.ready_round_count || 0} 輪`,
              tone: preview.ready ? "success" : "warning",
            },
            {
              label: "不完整 Round",
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

      <div className="grid gap-4 min-[900px]:grid-cols-2">
        <InnerPanel>
          <SubsectionHeader
            title="ArUco 基準"
            description="每張去畸變影像都以四角點估算公制世界座標姿態。"
            titleMode={1}
          />
          <InformationGrid
            items={[
              {
                label: "狀態",
                value: aruco.ready ? "可用" : "未就緒",
                tone: aruco.ready ? "success" : "error",
              },
              {
                label: "佈局版本",
                value: aruco.layout_version || "尚無資料",
              },
              {
                label: "Dictionary",
                value: aruco.dictionary || "尚無資料",
              },
              {
                label: "Marker 數量",
                value: displayNumber(aruco.marker_count, " 個"),
              },
              {
                label: "Marker 尺寸",
                value: displayNumber(aruco.marker_size_mm, " mm"),
              },
              {
                label: "世界單位",
                value: aruco.unit || "mm",
              },
            ]}
            rows={3}
          />
        </InnerPanel>

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
                value: backend.backend || setup.parameters.reconstructionBackend,
              },
              {
                label: "狀態",
                value: backend.available ? "可用" : "不可用",
                tone: backend.available ? "success" : "error",
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
                value: setup.parameters.qualityPreset,
              },
            ]}
            rows={3}
          />
        </InnerPanel>
      </div>

      <InnerPanel>
        <SubsectionHeader
          title="方法與輸出"
          description="原始 Record 保持唯讀，所有衍生資料寫入獨立分析目錄。"
          titleMode={1}
        />
        <InformationGrid
          items={[
            {
              label: "分析方法",
              value: method.label,
            },
            {
              label: "姿態精修",
              value: setup.parameters.useBundleAdjustment ? "啟用" : "停用",
            },
            {
              label: "Gaussian 模型",
              value: setup.parameters.saveGaussianModel ? "建立" : "不建立",
            },
            {
              label: "純植物點雲",
              value: setup.parameters.exportPlantPointCloud ? "建立" : "不建立",
            },
            {
              label: "植物骨架",
              value: setup.parameters.exportSkeleton ? "建立" : "不建立",
            },
            {
              label: "尖端標記",
              value: setup.parameters.exportTipMarkers ? "建立" : "不建立",
            },
            {
              label: "尖端標記軌跡",
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
      </InnerPanel>
    </section>
  );
}

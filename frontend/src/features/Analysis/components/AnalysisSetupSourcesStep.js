import {
  FiCheckCircle,
  FiFolder,
  FiRefreshCw,
} from "react-icons/fi";

import InformationGrid from "@/components/data/InformationGrid";
import SubsectionHeader from "@/components/headers/SubsectionHeader";
import { TextInput } from "@/components/inputs/Input";
import { ToggleRow } from "@/components/inputs/Toggle";
import InnerPanel from "@/components/panels/InnerPanel";
import { StatusPill } from "@/components/panels/Panel";

import AnalysisCaptureConfiguration from "./AnalysisCaptureConfiguration";
import AnalysisModeSelector from "./AnalysisModeSelector";
import { analysisCameraSourceRequired } from "../lib/analysisUtils";

const CAMERAS = [
  {
    id: "top",
    label: "俯視角",
  },
  {
    id: "side",
    label: "側視角",
  },
  {
    id: "rotating",
    label: "旋臂視角",
  },
];

function resolutionLabel(value) {
  return Array.isArray(value) && value.length === 2
    ? value.join(" × ")
    : "—";
}

export default function AnalysisSetupSourcesStep({
  record,
  setup,
  scanning,
  onModeSelectionChange,
  onCameraSourceChange,
}) {
  const preview = setup.sourcePreview;
  const previewDescription = [
    `共 ${preview?.round_count || 0} 輪；`,
    `${preview?.ready_round_count || 0} 輪可分析，`,
    `${preview?.incomplete_round_count || 0} 輪不完整。`,
  ].join(" ");

  return (
    <>
      <SubsectionHeader
        titleId="analysis-source-step-title"
        title="捕捉配置"
        description="顯示所選捕捉紀錄保存的根目錄與執行配置。"
      />

      <TextInput
        id="analysis-record-directory"
        label="紀錄根目錄"
        value={setup.recordPath}
        placeholder="請先在「選擇紀錄」步驟選擇紀錄"
        readOnly
      />

      {setup.recordId ? (
        <AnalysisCaptureConfiguration
          configuration={setup.captureConfiguration}
          record={record}
        />
      ) : null}

      {setup.recordId && setup.availableModes.length > 0 ? (
        <AnalysisModeSelector
          modes={setup.availableModes}
          selectedModeIds={setup.selectedModeIds}
          onSelectionChange={onModeSelectionChange}
        />
      ) : null}

      <InnerPanel
        mode="dark"
        aria-labelledby="analysis-camera-selection-title"
      >
        <SubsectionHeader
          titleId="analysis-camera-selection-title"
          title="分析視角"
          description="選擇這次分析要使用的攝影機視角。"
        />

        <div className="grid gap-3 min-[780px]:grid-cols-3">
          {CAMERAS.map((camera) => {
            const source = setup.cameraSources[camera.id];
            const required = analysisCameraSourceRequired(camera.id);

            return (
              <ToggleRow
                checked={required || source.enabled}
                label={`${camera.label}`}
                description={required
                  ? `${camera.label}是分析必要視角，固定保持啟用。`
                  : `決定是否將 ${camera.label}影像加入這次分析。`
                }
                disabled={required}
                onClick={() => onCameraSourceChange(
                  camera.id,
                  {
                    enabled: !source.enabled,
                  },
                )}
                key={camera.id}
              />
            );
          })}
        </div>
      </InnerPanel>

      <hr />
      <section
        className="grid gap-4"
        aria-labelledby="analysis-scan-result-title"
      >
        <SubsectionHeader
          titleId="analysis-scan-result-title"
          title="掃描配對"
          description={previewDescription}
        >
          <div className="flex flex-wrap items-center gap-2">
            {scanning ? (
              <StatusPill tone="warning">
                <FiRefreshCw
                  className="size-3.5 animate-spin"
                  aria-hidden="true"
                />
                自動掃描中
              </StatusPill>
            ) : preview?.ready ? (
              <StatusPill tone="success">
                <FiCheckCircle
                  className="size-3.5"
                  aria-hidden="true"
                />
                Round 配置有效
              </StatusPill>
            ) : (
              <StatusPill tone="neutral">
                <FiFolder
                  className="size-3.5"
                  aria-hidden="true"
                />
                尚未確認
              </StatusPill>
            )}
          </div>
        </SubsectionHeader>

        <dl className="grid gap-3 sm:grid-cols-3">
          {CAMERAS.map((camera) => (
            <InnerPanel
              key={camera.id}
            >
              <dt className="text-xs font-black text-neutral-200">
                {camera.label}
              </dt>
              <dd className="mt-1 m-0 text-sm font-black text-neutral-100">
                {preview?.camera_frame_counts?.[camera.id] || 0} 張 · {resolutionLabel(preview?.camera_resolutions?.[camera.id])} px
              </dd>
            </InnerPanel>
          ))}
        </dl>

        <InformationGrid
          items={[
            {
              label: "Round 數量",
              value: `${preview?.round_count || 0} 輪`,
            },
            {
              label: "有效 Round",
              value: `${preview?.ready_round_count || 0} 輪`,
              tone: preview?.ready ? "success" : "warning",
            },
            {
              label: "不完整 Round",
              value: `${preview?.incomplete_round_count || 0} 輪`,
              tone: preview?.incomplete_round_count > 0
                ? "warning"
                : "success",
            },
            {
              label: "總影像數",
              value: `${preview?.total_view_count || 0} 張`,
            },
          ]}
          columns={4}
          scroll
        />

        {preview?.round_readiness?.length > 0 ? (
          <div className="grid max-h-72 gap-2 overflow-y-auto pr-1">
            {preview.round_readiness.map((round) => (
              <InnerPanel
                className="gap-3 p-3"
                key={round.round_key}
                mode="dark"
              >
                <div className="flex min-w-0 items-center justify-between gap-3">
                  <span className="min-w-0 truncate text-sm font-black text-white">
                    {round.mode_id} / {round.round_id}
                  </span>
                  <StatusPill
                    tone={round.errors.length > 0 ? "offline" : "success"}
                  >
                    {round.errors.length > 0 ? "不完整" : "可分析"}
                  </StatusPill>
                </div>
                <InformationGrid
                  items={[
                    {
                      label: "影像",
                      value: `${round.view_count} 張`,
                    },
                    {
                      label: "俯視",
                      value: `${round.top_view_count} 張`,
                    },
                    {
                      label: "側視",
                      value: `${round.side_view_count} 張`,
                    },
                    {
                      label: "旋臂",
                      value: `${round.rotating_view_count} 張`,
                    },
                    {
                      label: "角度覆蓋",
                      value: round.angular_coverage_deg === null
                        ? "不適用"
                        : `${round.angular_coverage_deg}°`,
                    },
                    {
                      label: "捕捉時間",
                      value: round.duration_seconds === null
                        ? "尚無資料"
                        : `${round.duration_seconds.toFixed(2)} 秒`,
                    },
                  ]}
                  border="none"
                  columns={3}
                  scroll
                />
              </InnerPanel>
            ))}
          </div>
        ) : null}
      </section>
    </>
  );
}

import {
  FiCheckCircle,
  FiFolder,
  FiSearch,
} from "react-icons/fi";

import Button from "@/components/buttons/Button";
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
  onScan,
}) {
  const preview = setup.sourcePreview;
  const previewDescription = setup.method === "top_side_rotating"
    ? [
      `雙鏡頭可配對 ${preview?.pairable_frame_count || 0}`,
      `/ ${preview?.total_frame_count || 0} 組；`,
      `其中 ${preview?.rotating_pairable_frame_count || 0} 組含旋臂影像。`,
    ].join(" ")
    : [
      `可配對 ${preview?.pairable_frame_count || 0}`,
      `/ ${preview?.total_frame_count || 0} 組影格。`,
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
            {preview?.ready ? (
              <StatusPill tone="success">
                <FiCheckCircle
                  className="size-3.5"
                  aria-hidden="true"
                />
                配置與配對有效
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
            <Button
              className="ml-auto"
              disabled={scanning || !setup.recordPath}
              onClick={() => void onScan()}
            >
              <FiSearch
                className="size-4 shrink-0"
                aria-hidden="true"
              />
              {scanning ? "掃描中…" : "掃描"}
            </Button>
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
      </section>
    </>
  );
}

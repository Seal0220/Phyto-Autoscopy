import {
  FiCheckCircle,
  FiFolder,
  FiSearch,
} from "react-icons/fi";

import Button from "@/components/buttons/Button";
import SubsectionHeader from "@/components/headers/SubsectionHeader";
import { TextInput } from "@/components/inputs/Input";
import { ToggleRow } from "@/components/inputs/Toggle";
import { StatusPill } from "@/components/panels/Panel";

import AnalysisAvailableRecords from "./AnalysisAvailableRecords";

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
  sources,
  setup,
  scanning,
  onRecordSelect,
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
      <AnalysisAvailableRecords
        selectedRecordId={setup.recordId}
        sources={sources}
        onSelect={onRecordSelect}
      />

      <div
        className="h-px bg-white/10"
        aria-hidden="true"
      />

      <SubsectionHeader
        titleId="analysis-source-step-title"
        title="影像目錄"
        description="啟用的相機會形成同一份不可變分析輸入清單；路徑可在自動帶入後繼續修改。"
      />

      <div className="grid gap-3">
        {CAMERAS.map((camera) => {
          const source = setup.cameraSources[camera.id];

          return (
            <div
              className="grid min-w-0 gap-3 lg:grid-cols-[16rem_minmax(0,1fr)]"
              key={camera.id}
            >
              <ToggleRow
                checked={source.enabled}
                label={`${camera.label}（${camera.id}）`}
                description={`決定是否將 ${camera.id} 影像加入這次分析。`}
                onClick={() => onCameraSourceChange(
                  camera.id,
                  {
                    enabled: !source.enabled,
                  },
                )}
              />
              <TextInput
                id={`analysis-${camera.id}-directory`}
                label={`${camera.id} 目錄`}
                value={source.path}
                disabled={!source.enabled}
                onValueChange={(path) => onCameraSourceChange(
                  camera.id,
                  {
                    path,
                  },
                )}
              />
            </div>
          );
        })}
      </div>

      <div className="flex flex-wrap items-center gap-2">
        {preview?.ready ? (
          <StatusPill tone="success">
            <FiCheckCircle
              className="size-3.5"
              aria-hidden="true"
            />
            目錄與配對有效
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
          disabled={scanning}
          onClick={() => void onScan()}
        >
          <FiSearch
            className="size-4 shrink-0"
            aria-hidden="true"
          />
          {scanning ? "掃描中…" : "掃描目錄"}
        </Button>
      </div>

      {preview ? (
        <section
          className="grid gap-4 border-t border-white/10 pt-5"
          aria-labelledby="analysis-scan-result-title"
        >
          <SubsectionHeader
            titleId="analysis-scan-result-title"
            title="掃描結果"
            description={previewDescription}
          />
          <dl className="grid gap-3 sm:grid-cols-3">
            {CAMERAS.map((camera) => (
              <div
                className="rounded-xl border border-white/10 bg-black/10 p-3"
                key={camera.id}
              >
                <dt className="text-xs font-black text-neutral-500">
                  {camera.label}
                </dt>
                <dd className="mt-1 m-0 text-sm font-black text-neutral-100">
                  {preview.camera_frame_counts?.[camera.id] || 0} 張 · {resolutionLabel(
                    preview.camera_resolutions?.[camera.id],
                  )}
                </dd>
              </div>
            ))}
          </dl>
        </section>
      ) : null}
    </>
  );
}

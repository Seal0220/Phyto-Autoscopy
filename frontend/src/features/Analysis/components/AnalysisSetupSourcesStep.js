import {
  FiCheckCircle,
  FiFolder,
  FiSearch,
} from "react-icons/fi";

import Button from "@/components/buttons/Button";
import { SelectInput, TextInput } from "@/components/inputs/Input";
import { ToggleRow } from "@/components/inputs/Toggle";
import InnerPanel from "@/components/panels/InnerPanel";
import { StatusPill } from "@/components/panels/Panel";
import SubsectionHeader from "@/components/headers/SubsectionHeader";

import { ANALYSIS_METHODS } from "../analysisConfig";

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
    label: "環繞視角",
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
  onMethodChange,
  onCameraSourceChange,
  onScan,
}) {
  const preview = setup.sourcePreview;
  const previewDescription = setup.method === "top_side_rotating"
    ? [
      `雙目可配對 ${preview?.pairable_frame_count || 0}`,
      `/ ${preview?.total_frame_count || 0} 組；`,
      `其中 ${preview?.rotating_pairable_frame_count || 0} 組含環繞影像。`,
    ].join(" ")
    : [
      `可配對 ${preview?.pairable_frame_count || 0}`,
      `/ ${preview?.total_frame_count || 0} 組影格。`,
    ].join(" ");

  return (
    <section
      className="grid gap-5"
      aria-labelledby="analysis-source-step-title"
    >
      <SubsectionHeader
        titleId="analysis-source-step-title"
        title="分析方法與影像目錄"
        description="可由紀錄自動帶入後再修改，也可不選紀錄並直接填寫三個相機目錄。"
      />

      <div className="grid gap-3 md:grid-cols-2">
        {Object.entries(ANALYSIS_METHODS).map(([methodId, method]) => (
          <label
            className={`grid cursor-pointer gap-2 rounded-[22px] border p-4 transition-[background-color,border-color] duration-200 focus-within:outline-2 focus-within:outline-emerald-300 ${
              setup.method === methodId
                ? "border-emerald-200/75 bg-emerald-500/20"
                : "border-white/10 bg-white/6 hover:border-emerald-200/35 hover:bg-white/9"
            }`}
            key={methodId}
          >
            <input
              className="sr-only"
              type="radio"
              name="analysis-method"
              value={methodId}
              checked={setup.method === methodId}
              onChange={() => onMethodChange(methodId)}
            />
            <span className="text-sm font-black tracking-widest text-emerald-200">
              {method.label}
            </span>
            <span className="text-xs font-semibold leading-5 text-neutral-400">
              {method.description}
            </span>
          </label>
        ))}
      </div>

      <InnerPanel>
        <SubsectionHeader
          title="影像目錄"
          description="啟用的相機會形成同一份不可變分析輸入清單。"
        />

        <SelectInput
          id="analysis-record-autofill"
          label="自動帶入"
          value={setup.recordId}
          options={[
            {
              value: "",
              label: "無（手動填寫）",
            },
            ...sources.map((source) => ({
              value: source.record_id,
              label: source.record_id,
            })),
          ]}
          description="只負責填入目錄；填入後仍可修改路徑或關閉相機。"
          onValueChange={onRecordSelect}
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
      </InnerPanel>

      {preview ? (
        <InnerPanel>
          <SubsectionHeader
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
          {preview.errors?.length ? (
            <ul className="m-0 grid gap-1 pl-5 text-xs font-semibold text-amber-200">
              {preview.errors.map((error) => (
                <li key={error}>{error}</li>
              ))}
            </ul>
          ) : null}
        </InnerPanel>
      ) : null}
    </section>
  );
}

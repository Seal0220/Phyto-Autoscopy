import { FiRefreshCw, FiX } from "react-icons/fi";

import Button from "@/components/buttons/Button";
import InformationGrid from "@/components/data/InformationGrid";
import SubsectionHeader from "@/components/headers/SubsectionHeader";
import { TextInput } from "@/components/inputs/Input";
import { ToggleRow } from "@/components/inputs/Toggle";
import DisclosurePanel from "@/components/panels/DisclosurePanel";
import { StatusPill } from "@/components/panels/Panel";
import { formatNumberWithUnit } from "@/lib/formatUtils";

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
  scanProgress,
  scanError,
  onRescan,
  onCancelScan,
  onModeSelectionChange,
  onCameraSourceChange,
}) {
  const preview = setup.sourcePreview;
  const previewDescription = scanning
    ? scanProgress?.total > 0
      ? scanProgress.processed >= scanProgress.total
        ? "影像檢查完成，正在整理各輪配對結果。"
        : `已檢查 ${scanProgress.processed} / ${scanProgress.total} 筆影像索引。`
      : "正在讀取影像索引並準備掃描。"
    : scanError
      ? "掃描未完成，請重新掃描。"
      : preview
        ? `${preview.ready_round_count || 0} / ${preview.round_count || 0} 輪可分析。`
        : "選擇擷取模式後會自動掃描。";

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

      <section
        className="grid gap-3 border-t border-white/15 pt-4"
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
      </section>

      <hr className="border-white/15" />
      <section
        className="grid gap-4"
        aria-labelledby="analysis-round-scan-title"
      >
        <SubsectionHeader
          titleId="analysis-round-scan-title"
          title="影像掃描"
          description={previewDescription}
        >
          <div className="flex flex-wrap items-center justify-end gap-2">
            <StatusPill tone={scanError ? "offline" : scanning
              ? "warning"
              : preview?.ready
                ? "success"
                : preview
                  ? "offline"
                  : "neutral"
            }>
              {scanError
                ? "掃描失敗"
                : scanning
                  ? "掃描中"
                  : preview?.ready
                    ? "資料有效"
                    : preview
                      ? "需處理"
                      : "尚未掃描"
              }
            </StatusPill>
            <Button
              disabled={!scanning && (!setup.recordPath || setup.selectedModeIds.length === 0)}
              onClick={() => void (scanning ? onCancelScan() : onRescan())}
            >
              {scanning ? (
                <FiX
                  className="size-4 shrink-0"
                  aria-hidden="true"
                />
              ) : (
                <FiRefreshCw
                  className="size-4 shrink-0"
                  aria-hidden="true"
                />
              )}
              {scanning ? "取消掃描" : "重新掃描"}
            </Button>
          </div>
        </SubsectionHeader>

        <InformationGrid
          items={[
            {
              label: "輪次數量",
              value: formatNumberWithUnit(preview?.round_count, "輪"),
            },
            {
              label: "有效輪次",
              value: formatNumberWithUnit(preview?.ready_round_count, "輪"),
              tone: !preview ? "neutral" : preview.ready ? "success" : "warning",
            },
            {
              label: "不完整輪次",
              value: formatNumberWithUnit(preview?.incomplete_round_count, "輪"),
              tone: !preview ? "neutral" : preview.incomplete_round_count > 0
                ? "warning"
                : "success",
            },
            {
              label: "總影像數",
              value: formatNumberWithUnit(preview?.total_view_count, "張"),
            },
            {
              label: "GPU 解碼",
              value: formatNumberWithUnit(preview?.image_probe_backends?.gpu, "張"),
            },
            {
              label: "CPU 解碼",
              value: formatNumberWithUnit(preview?.image_probe_backends?.cpu, "張"),
            },
          ]}
          rows={2}
          stackAtSmall
        />

        <InformationGrid
          items={CAMERAS.map((camera) => ({
            label: camera.label,
            value: setup.cameraSources[camera.id]?.enabled
              ? preview
                ? `${preview.camera_frame_counts?.[camera.id] || 0} 張 · ${resolutionLabel(preview.camera_resolutions?.[camera.id])} px`
                : "尚無資料"
              : "未啟用",
            tone: preview && setup.cameraSources[camera.id]?.enabled ? "success" : "neutral",
          }))}
          border="none"
          rows={1}
          scroll
        />

        {preview?.round_readiness?.length > 0 ? (
          <DisclosurePanel
            title={`各輪掃描明細 · 顯示 ${preview.round_readiness.length} / ${preview.round_count} 輪`}
          >
            <div className="grid max-h-72 gap-3 overflow-y-auto">
              {preview.omitted_round_count > 0 ? (
                <p className="text-xs font-semibold text-neutral-400">
                  明細優先顯示不完整輪次，最多 {preview.round_readiness.length} 輪；上方統計包含全部輪次。
                </p>
              ) : null}
              {preview.round_readiness.map((round) => (
                <div
                  className="grid min-w-0 gap-2 border-b border-white/10 pb-3 last:border-b-0 last:pb-0"
                  key={round.round_key}
                >
                  <div className="flex min-w-0 items-center justify-between gap-3">
                    <span className="min-w-0 truncate text-xs font-black text-neutral-200">
                      {round.mode_id} / {round.round_id}
                      {round.snapshot_id ? ` / ${round.snapshot_id}` : ""}
                    </span>
                    <StatusPill tone={round.errors?.length ? "offline" : "success"}>
                      {round.errors?.length ? "不完整" : "可分析"}
                    </StatusPill>
                  </div>
                  <InformationGrid
                    items={[
                      { label: "影像", value: `${round.view_count} 張` },
                      { label: "俯視", value: `${round.top_view_count} 張` },
                      { label: "側視", value: `${round.side_view_count} 張` },
                      { label: "旋臂", value: `${round.rotating_view_count} 張` },
                      {
                        label: "角度覆蓋",
                        value: round.angular_coverage_deg === null
                          ? "不適用"
                          : `${round.angular_coverage_deg}°`,
                      },
                      {
                        label: "捕捉時間",
                        value: formatNumberWithUnit(round.duration_seconds, "秒"),
                      },
                    ]}
                    border="none"
                    rows={2}
                    scroll
                  />
                </div>
              ))}
            </div>
          </DisclosurePanel>
        ) : null}
      </section>
    </>
  );
}

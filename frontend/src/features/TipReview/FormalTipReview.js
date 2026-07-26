"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import {
  FiAlertTriangle,
  FiBox,
  FiCheck,
  FiEdit3,
  FiMousePointer,
  FiRefreshCw,
  FiSave,
  FiTrash2,
} from "react-icons/fi";
import { PiHouseFill } from "react-icons/pi";

import ActionRow from "@/components/actions/ActionRow";
import Button from "@/components/buttons/Button";
import InformationGrid from "@/components/data/InformationGrid";
import SubsectionHeader from "@/components/headers/SubsectionHeader";
import {
  NumericInput,
  TextInput,
} from "@/components/inputs/Input";
import FullscreenImage from "@/components/media/FullscreenImage";
import InnerPanel from "@/components/panels/InnerPanel";
import {
  Panel,
  PanelHeader,
  StatusPill,
} from "@/components/panels/Panel";
import {
  ANALYSIS_MODEL_STATUS_META,
  ANALYSIS_METHODS,
  RECONSTRUCTION_BACKEND_LABELS,
} from "@/features/Analysis/analysisConfig";
import { analysisRunDisplay } from "@/features/AnalysisRun/lib/analysisRunUtils";
import useNotificationsContext from "@/features/Notifications/hooks/useNotificationsContext";
import { formatDateTime } from "@/lib/formatUtils";

import FormalTipReviewRoundImage from "./components/FormalTipReviewRoundImage";
import useFormalTipReview from "./hooks/useFormalTipReview";
import { formalArtifactUrl } from "./lib/formalTipReviewApiUtils";

const TIP_SOURCE_LABELS = {
  multiview_joint: "多視角聯合分析",
  fixed_triangulation: "固定雙鏡頭三角化",
  model_skeleton: "模型骨架推定",
  temporal_estimate: "時序估計",
  manual: "人工修正",
  invalid: "無效",
};

function displayNumber(
  value,
  suffix = "",
  digits = 2,
) {
  const number = Number(value);
  return Number.isFinite(number)
    ? `${number.toFixed(digits)}${suffix}`
    : "尚無資料";
}

function roundStatus(item, landmark) {
  if (landmark?.valid && item.status === "tip_completed") {
    return {
      label: "可用",
      tone: "success",
    };
  }
  if (landmark?.valid) {
    return {
      label: "僅尖端標記",
      tone: "warning",
    };
  }
  return {
    label: "需確認",
    tone: "offline",
  };
}

export default function FormalTipReview({
  analysisId,
}) {
  const router = useRouter();
  const { showNotification } = useNotificationsContext();
  const {
    run,
    rounds,
    landmarks,
    selectedRound,
    selectedViews,
    selectedModel,
    automaticLandmark,
    resolvedLandmark,
    selectedObservations,
    roundCorrections,
    latestCorrection,
    draft,
    loading,
    loadError,
    pendingAction,
    mutationError,
    load,
    selectRound,
    updateDraft,
    updateObservation,
    removeObservation,
    saveCorrection,
    deleteCorrection,
    completeReview,
  } = useFormalTipReview({
    analysisId,
  });
  const runDisplay = analysisRunDisplay(run);
  const locked = Boolean(pendingAction);

  useEffect(() => {
    const error = mutationError || loadError;
    if (error) showNotification(error, "error");
  }, [
    loadError,
    mutationError,
    showNotification,
  ]);

  const selectedStatus = selectedRound
    ? roundStatus(selectedRound, resolvedLandmark)
    : null;
  const modelQuality = selectedModel?.model_quality || {};
  const modelStatus = ANALYSIS_MODEL_STATUS_META[
    selectedModel?.status
  ] || {
    label: "尚無模型",
    tone: "neutral",
  };
  const overviewItems = selectedRound ? [
    {
      label: "模式",
      value: selectedRound.mode_id,
    },
    {
      label: "Round",
      value: selectedRound.round_id,
    },
    {
      label: "有效視角",
      value: `${selectedRound.view_count || 0} 個`,
    },
    {
      label: "旋臂涵蓋",
      value: displayNumber(selectedRound.angular_coverage_deg, "°", 1),
    },
    {
      label: "尖端標記信心",
      value: displayNumber(
        resolvedLandmark ? resolvedLandmark.confidence * 100 : null,
        "%",
        1,
      ),
      tone: resolvedLandmark?.valid ? "success" : "error",
    },
    {
      label: "標記來源",
      value: TIP_SOURCE_LABELS[resolvedLandmark?.source] || "尚無資料",
    },
    {
      label: "平均重投影誤差",
      value: displayNumber(
        resolvedLandmark?.mean_reprojection_error_px,
        " px",
        3,
      ),
    },
    {
      label: "支持視角",
      value: `${resolvedLandmark?.visible_view_count || 0} 個`,
    },
  ] : [];
  const automaticCoordinateItems = [
    {
      label: "X",
      value: displayNumber(automaticLandmark?.x_mm, " mm", 3),
    },
    {
      label: "Y",
      value: displayNumber(automaticLandmark?.y_mm, " mm", 3),
    },
    {
      label: "Z",
      value: displayNumber(automaticLandmark?.z_mm, " mm", 3),
    },
    {
      label: "信心",
      value: displayNumber(
        automaticLandmark ? automaticLandmark.confidence * 100 : null,
        "%",
        1,
      ),
    },
  ];
  const resolvedCoordinateItems = [
    {
      label: "X",
      value: displayNumber(resolvedLandmark?.x_mm, " mm", 3),
    },
    {
      label: "Y",
      value: displayNumber(resolvedLandmark?.y_mm, " mm", 3),
    },
    {
      label: "Z",
      value: displayNumber(resolvedLandmark?.z_mm, " mm", 3),
    },
    {
      label: "模型距離",
      value: displayNumber(resolvedLandmark?.distance_to_model_mm, " mm", 3),
    },
    {
      label: "骨架距離",
      value: displayNumber(resolvedLandmark?.distance_to_skeleton_mm, " mm", 3),
    },
    {
      label: "時序位移",
      value: displayNumber(resolvedLandmark?.temporal_distance_mm, " mm", 3),
    },
  ];

  return (
    <div className="mx-auto grid w-full max-w-[112.5rem] gap-4 pt-24 max-[980px]:pt-32">
      <Panel aria-label="三維尖端標記人工確認">
        <PanelHeader
          title="尖端標記人工確認"
          action={(
            <div className="flex flex-wrap items-center justify-end gap-2">
              {run ? (
                <StatusPill tone={runDisplay.status.tone}>
                  {runDisplay.status.label}
                </StatusPill>
              ) : null}
              <Button
                disabled={loading}
                onClick={() => void load()}
              >
                <FiRefreshCw
                  className="size-4 shrink-0"
                  aria-hidden="true"
                />
                {loading ? "讀取中…" : "重新讀取"}
              </Button>
              <Button
                onClick={() => router.push(
                  `/analysis/${encodeURIComponent(analysisId)}`,
                )}
              >
                <PiHouseFill
                  className="size-4 shrink-0"
                  aria-hidden="true"
                />
                返回分析紀錄
              </Button>
            </div>
          )}
        />

        <div className="grid gap-4 p-5 max-sm:p-4">
          {loading && !run ? (
            <div className="grid min-h-36 place-items-center rounded-xl border border-white/15 bg-black/15 p-4 text-sm font-semibold text-neutral-400">
              讀取尖端標記與每輪模型中…
            </div>
          ) : null}

          {run ? (
            <div className="grid min-w-0 gap-4 min-[1080px]:grid-cols-[18rem_minmax(0,1fr)]">
              <InnerPanel className="min-h-0 content-start">
                <SubsectionHeader
                  title="Round"
                  description={`${rounds.length} 輪；逐輪檢查模型、重投影與尖端標記。`}
                />
                <div className="grid max-h-[42rem] gap-2 overflow-y-auto pr-1">
                  {rounds.map((item) => {
                    const landmark = landmarks.find(
                      (entry) => entry.round_key === item.round_key,
                    );
                    const status = roundStatus(item, landmark);
                    const selected = item.round_key === selectedRound?.round_key;

                    return (
                      <button
                        type="button"
                        className={`grid min-w-0 cursor-pointer grid-cols-[minmax(0,1fr)_auto] items-center gap-3 rounded-xl border px-3 py-2 text-left transition-colors duration-150 focus-visible:outline-2 focus-visible:outline-emerald-300 ${
                          selected
                            ? "border-emerald-200/70 bg-emerald-400/15"
                            : "border-white/15 bg-black/15 hover:border-white/25 hover:bg-white/7"
                        }`}
                        key={item.round_key}
                        aria-pressed={selected}
                        onClick={() => selectRound(item.round_key)}
                      >
                        <span className="min-w-0">
                          <span className="block truncate text-sm font-black text-white">
                            {item.round_id}
                          </span>
                          <span className="mt-0.5 block truncate text-xs font-semibold text-neutral-500">
                            {item.mode_id}
                          </span>
                        </span>
                        <StatusPill tone={status.tone}>
                          {status.label}
                        </StatusPill>
                      </button>
                    );
                  })}
                </div>
              </InnerPanel>

              {selectedRound ? (
                <div className="grid min-w-0 gap-4">
                  <InnerPanel>
                    <SubsectionHeader
                      title={`${selectedRound.mode_id} / ${selectedRound.round_id}`}
                      description={ANALYSIS_METHODS[run.method_name]?.description}
                    >
                      {selectedStatus ? (
                        <StatusPill tone={selectedStatus.tone}>
                          {selectedStatus.label}
                        </StatusPill>
                      ) : null}
                    </SubsectionHeader>
                    <InformationGrid
                      items={overviewItems}
                      rows={2}
                      minimumColumnWidth
                      scroll
                    />
                    <div className="grid gap-3 min-[780px]:grid-cols-2">
                      <div className="grid min-w-0 content-start gap-2">
                        <h4 className="m-0 text-xs font-black text-neutral-300">
                          原始自動尖端標記
                        </h4>
                        <InformationGrid
                          items={automaticCoordinateItems}
                          rows={2}
                          minimumColumnWidth
                          scroll
                        />
                      </div>
                      <div className="grid min-w-0 content-start gap-2">
                        <h4 className="m-0 text-xs font-black text-neutral-300">
                          目前採用尖端標記
                        </h4>
                        <InformationGrid
                          items={resolvedCoordinateItems}
                          rows={3}
                          minimumColumnWidth
                          scroll
                        />
                      </div>
                    </div>
                    {resolvedLandmark?.failure_reason ? (
                      <p className="m-0 rounded-xl border border-amber-200/25 bg-amber-500/10 p-3 text-sm font-semibold text-amber-200">
                        {resolvedLandmark.failure_reason === "manual_invalid"
                          ? "操作人員已將此 Round 標記為尖端不可確認。"
                          : resolvedLandmark.failure_reason
                        }
                      </p>
                    ) : null}
                  </InnerPanel>

                  <InnerPanel>
                    <SubsectionHeader
                      title="每輪植物模型"
                      description="模型預覽、完整場景與純植物輸出均屬於目前 Round。"
                    >
                      <StatusPill tone={modelStatus.tone}>
                        {modelStatus.label}
                      </StatusPill>
                    </SubsectionHeader>
                    {selectedModel?.preview_paths?.length ? (
                      <div className="grid gap-3 min-[720px]:grid-cols-2 min-[1200px]:grid-cols-3">
                        {selectedModel.preview_paths.map((path, index) => {
                          const url = formalArtifactUrl(analysisId, path);
                          return (
                            <div
                              className="relative overflow-hidden rounded-xl border border-white/15 bg-black"
                              key={path}
                            >
                              <img
                                className="block aspect-video w-full object-contain"
                                src={url}
                                alt={`每輪植物模型預覽 ${index + 1}`}
                              />
                              <FullscreenImage
                                src={url}
                                alt={`每輪植物模型預覽 ${index + 1}`}
                                label={`模型預覽 ${index + 1}`}
                              />
                            </div>
                          );
                        })}
                      </div>
                    ) : (
                      <p className="m-0 rounded-xl border border-dashed border-white/15 bg-black/15 p-5 text-center text-sm font-semibold text-neutral-400">
                        此 Round 尚無可顯示的模型預覽。
                      </p>
                    )}
                    <InformationGrid
                      items={[
                        {
                          label: "模型後端",
                          value: RECONSTRUCTION_BACKEND_LABELS[
                            selectedModel?.backend
                          ] || "尚無資料",
                        },
                        {
                          label: "Gaussian 數量",
                          value: selectedModel?.gaussian_count ?? "尚無資料",
                        },
                        {
                          label: "完整點數",
                          value: selectedModel?.point_count ?? "尚無資料",
                        },
                        {
                          label: "植物點數比例",
                          value: displayNumber(
                            modelQuality.plant_isolation?.retained_ratio != null
                              ? modelQuality.plant_isolation.retained_ratio * 100
                              : null,
                            "%",
                            1,
                          ),
                        },
                        {
                          label: "骨架節點",
                          value: modelQuality.skeleton_node_count ?? "尚無資料",
                        },
                        {
                          label: "骨架端點",
                          value: modelQuality.skeleton_endpoint_count ?? "尚無資料",
                        },
                      ]}
                      rows={2}
                      minimumColumnWidth
                      scroll
                    />
                  </InnerPanel>

                  <InnerPanel>
                    <SubsectionHeader
                      title="各視角尖端標記"
                      description="重投影圖會同時顯示候選、採用點與最終三維標記；視角修正模式下可直接點選。"
                    >
                      <StatusPill tone={selectedObservations.some((item) => item.selected) ? "success" : "warning"}>
                        {selectedObservations.filter((item) => item.selected).length} 個支持候選
                      </StatusPill>
                    </SubsectionHeader>
                    <div className="grid min-w-0 gap-3 min-[780px]:grid-cols-2 min-[1280px]:grid-cols-3">
                      {selectedViews.map((view, viewIndex) => (
                        <FormalTipReviewRoundImage
                          analysisId={analysisId}
                          key={view.view_id}
                          view={view}
                          viewIndex={viewIndex}
                          point={draft.observations[view.view_id] || null}
                          disabled={locked || draft.mode !== "views"}
                          onPointChange={updateObservation}
                          onPointRemove={removeObservation}
                        />
                      ))}
                    </div>
                  </InnerPanel>

                  <InnerPanel>
                    <SubsectionHeader
                      title="人工修正"
                      description="修正會建立歷史版本；原始自動尖端標記不會被覆寫。"
                    />
                    <div className="grid gap-2 min-[680px]:grid-cols-3">
                      {[
                        ["views", "多視角指定", FiMousePointer],
                        ["point", "三維位置", FiBox],
                        ["invalid", "尖端不可確認", FiAlertTriangle],
                      ].map(([mode, label, Icon]) => (
                        <Button
                          key={mode}
                          variant={draft.mode === mode ? "primary" : "default"}
                          disabled={locked}
                          aria-pressed={draft.mode === mode}
                          onClick={() => updateDraft("mode", mode)}
                        >
                          <Icon
                            className="size-4 shrink-0"
                            aria-hidden="true"
                          />
                          {label}
                        </Button>
                      ))}
                    </div>

                    {draft.mode === "point" ? (
                      <div className="grid gap-3 min-[680px]:grid-cols-3">
                        {[
                          ["x", "尖端 X"],
                          ["y", "尖端 Y"],
                          ["z", "尖端 Z"],
                        ].map(([axis, label]) => (
                          <NumericInput
                            id={`tip-correction-${axis}`}
                            key={axis}
                            label={label}
                            value={draft.point[axis]}
                            disabled={locked}
                            step={0.1}
                            suffix="mm"
                            onValueChange={(value) => updateDraft("point", {
                              ...draft.point,
                              [axis]: value,
                            })}
                          />
                        ))}
                      </div>
                    ) : null}

                    {draft.mode === "invalid" ? (
                      <p className="m-0 rounded-xl border border-rose-300/25 bg-rose-500/10 p-3 text-sm font-semibold text-rose-200">
                        儲存後此 Round 的解析結果會保留，但尖端標記將記為不可確認，軌跡不會強制填補此缺口。
                      </p>
                    ) : null}

                    <TextInput
                      id="formal-tip-correction-reason"
                      label="修正原因"
                      value={draft.reason}
                      disabled={locked}
                      maxLength={1000}
                      onValueChange={(value) => updateDraft("reason", value)}
                    />

                    <ActionRow className="w-full">
                      {latestCorrection ? (
                        <Button
                          variant="dangerGhost"
                          disabled={locked}
                          onClick={() => void deleteCorrection(
                            latestCorrection.correction_id,
                          )}
                        >
                          <FiTrash2
                            className="size-4 shrink-0"
                            aria-hidden="true"
                          />
                          {pendingAction === `delete-${latestCorrection.correction_id}`
                            ? "刪除中…"
                            : "刪除最新修正"
                          }
                        </Button>
                      ) : null}
                      <Button
                        className="ml-auto"
                        variant="primary"
                        disabled={locked}
                        onClick={() => void saveCorrection()}
                      >
                        <FiSave
                          className="size-4 shrink-0"
                          aria-hidden="true"
                        />
                        {pendingAction === "save" ? "儲存中…" : "儲存修正"}
                      </Button>
                    </ActionRow>
                  </InnerPanel>

                  <InnerPanel>
                    <SubsectionHeader
                      title="修正歷史"
                      description={`${roundCorrections.length} 筆；最末一筆是目前套用版本。`}
                    />
                    {roundCorrections.length ? (
                      <div className="grid max-h-80 gap-2 overflow-y-auto pr-1">
                        {[...roundCorrections].reverse().map((item, index) => (
                          <div
                            className="grid gap-2 rounded-xl border border-white/15 bg-black/15 p-3"
                            key={item.correction_id}
                          >
                            <div className="flex min-w-0 items-center justify-between gap-2">
                              <span className="truncate text-sm font-black text-white">
                                {item.invalid ? "尖端不可確認" : "人工尖端標記"}
                              </span>
                              <StatusPill tone={index === 0 ? "success" : "neutral"}>
                                {index === 0 ? "目前版本" : "歷史版本"}
                              </StatusPill>
                            </div>
                            <p className="m-0 text-sm font-semibold text-neutral-300">
                              {item.reason}
                            </p>
                            <p className="m-0 text-xs font-semibold text-neutral-500">
                              {item.operator_id}・
                              {item.correction_type === "point"
                                ? "三維位置"
                                : item.correction_type === "invalid"
                                  ? "不可確認"
                                  : "多視角指定"
                              }・
                              {formatDateTime(item.created_at)}・
                              修正後誤差 {displayNumber(item.reprojection_after_px, " px", 3)}
                            </p>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <p className="m-0 py-3 text-center text-sm font-semibold text-neutral-400">
                        此 Round 尚無人工修正。
                      </p>
                    )}
                  </InnerPanel>
                </div>
              ) : null}
            </div>
          ) : null}

          {run && [
            "needs_review",
            "reviewing",
            "completed",
            "partially_completed",
          ].includes(run.status) ? (
            <ActionRow className="w-full">
              <Button
                onClick={() => router.push(
                  `/analysis/${encodeURIComponent(analysisId)}`,
                )}
              >
                <FiEdit3
                  className="size-4 shrink-0"
                  aria-hidden="true"
                />
                返回執行詳情
              </Button>
              <Button
                className="ml-auto"
                variant="primary"
                disabled={locked}
                onClick={async () => {
                  const completed = await completeReview();
                  if (completed) {
                    router.push(
                      `/analysis/${encodeURIComponent(analysisId)}/results`,
                    );
                  }
                }}
              >
                <FiCheck
                  className="size-4 shrink-0"
                  aria-hidden="true"
                />
                {pendingAction === "complete"
                  ? "完成確認中…"
                  : "完成尖端標記確認"
                }
              </Button>
            </ActionRow>
          ) : null}
        </div>
      </Panel>
    </div>
  );
}

"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import {
  FiDownload,
  FiEdit3,
  FiRefreshCw,
} from "react-icons/fi";
import { PiHouseFill } from "react-icons/pi";

import Button from "@/components/buttons/Button";
import StatusCard from "@/components/cards/StatusCard";
import InformationGrid from "@/components/data/InformationGrid";
import SubsectionHeader from "@/components/headers/SubsectionHeader";
import InnerPanel from "@/components/panels/InnerPanel";
import {
  Panel,
  PanelHeader,
  StatusPill,
} from "@/components/panels/Panel";
import {
  ANALYSIS_METHODS,
  ANALYSIS_MODEL_STATUS_META,
  RECONSTRUCTION_BACKEND_LABELS,
} from "@/features/Analysis/analysisConfig";
import { analysisRunDisplay } from "@/features/AnalysisRun/lib/analysisRunUtils";
import useNotificationsContext from "@/features/Notifications/hooks/useNotificationsContext";
import { formatDateTime } from "@/lib/formatUtils";

import FormalTrajectoryViewer3D from "./components/FormalTrajectoryViewer3D";
import FormalTrajectoryCharts from "./components/FormalTrajectoryCharts";
import TrajectoryViewerModelOutputs from "./components/TrajectoryViewerModelOutputs";
import useFormalTrajectoryResults from "./hooks/useFormalTrajectoryResults";
import {
  TRAJECTORY_DETECTION_LABELS,
  TRAJECTORY_ROTATION_LABELS,
} from "./trajectoryViewerConfig";

function displayNumber(
  value,
  suffix = "",
  digits = 2,
) {
  if (value === null || value === undefined || value === "") {
    return "尚無資料";
  }
  const number = Number(value);
  return Number.isFinite(number)
    ? `${number.toFixed(digits)}${suffix}`
    : "尚無資料";
}

function resolvedLandmarks(
  landmarks,
  corrections,
) {
  const resolved = new Map(
    landmarks.map((item) => [item.round_key, item]),
  );
  for (const correction of corrections) {
    resolved.set(correction.round_key, correction.corrected_tip);
  }
  return resolved;
}

export default function FormalTrajectoryViewer({
  analysisId,
}) {
  const router = useRouter();
  const { showNotification } = useNotificationsContext();
  const {
    run,
    rounds,
    models,
    landmarks,
    corrections,
    trajectory,
    quality,
    loading,
    loadError,
    exportPending,
    exportError,
    load,
    downloadExport,
  } = useFormalTrajectoryResults({
    analysisId,
  });

  useEffect(() => {
    const error = exportError || loadError;
    if (error) showNotification(error, "error");
  }, [
    exportError,
    loadError,
    showNotification,
  ]);

  const runDisplay = analysisRunDisplay(run);
  const resolved = resolvedLandmarks(landmarks, corrections);
  const modelsByRound = new Map(
    models.map((item) => [item.round_key, item]),
  );
  const validPoints = trajectory.filter((item) => item.valid);
  const missingPoints = trajectory.filter((item) => !item.valid).length;
  const completedModels = models.filter(
    (item) => item.status === "completed",
  ).length;
  const modes = Object.entries(quality?.modes || {});

  return (
    <div className="mx-auto grid w-full max-w-[112.5rem] gap-4 pt-24 max-[980px]:pt-32">
      <Panel aria-label="正式分析結果">
        <PanelHeader
          title="分析結果"
          action={(
            <div className="flex flex-wrap items-center justify-end gap-2">
              {run ? (
                <StatusPill tone={runDisplay.status.tone}>
                  {runDisplay.status.label}
                </StatusPill>
              ) : null}
              {loadError ? (
                <Button
                  disabled={loading}
                  onClick={() => void load()}
                >
                  <FiRefreshCw
                    className={`size-4 shrink-0 ${
                      loading ? "animate-spin" : ""
                    }`}
                    aria-hidden="true"
                  />
                  {loading ? "重新讀取中…" : "重新讀取"}
                </Button>
              ) : null}
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
              <Button
                onClick={() => router.push(
                  `/analysis/${encodeURIComponent(analysisId)}/review`,
                )}
              >
                <FiEdit3
                  className="size-4 shrink-0"
                  aria-hidden="true"
                />
                檢查尖端標記
              </Button>
              <Button
                variant="primary"
                disabled={exportPending || !run}
                onClick={() => void downloadExport()}
              >
                <FiDownload
                  className="size-4 shrink-0"
                  aria-hidden="true"
                />
                {exportPending ? "匯出中…" : "匯出結果"}
              </Button>
            </div>
          )}
        />

        <div className="grid gap-4 p-5 max-sm:p-4">
          {loading && !run ? (
            <div className="grid min-h-36 place-items-center rounded-xl border border-white/15 bg-black/15 p-4 text-sm font-semibold text-neutral-400">
              讀取每輪模型與尖端標記軌跡中…
            </div>
          ) : null}

          {run ? (
            <>
              <div className="grid gap-3 min-[520px]:grid-cols-2 min-[980px]:grid-cols-5">
                <StatusCard
                  title="分析 Round"
                  content={rounds.length}
                  note="輪"
                />
                <StatusCard
                  title="完成模型"
                  content={completedModels}
                  note={`共 ${models.length} 個模型紀錄`}
                />
                <StatusCard
                  title="可用軌跡點"
                  content={validPoints.length}
                  note={`實測率 ${displayNumber(quality.valid_measurement_ratio * 100, "%", 1)}`}
                />
                <StatusCard
                  title="插值軌跡點"
                  content={quality.interpolated_point_count || 0}
                  note="只補單一缺失 Round"
                />
                <StatusCard
                  title="缺失區段"
                  content={missingPoints}
                  note="未自動插值"
                />
              </div>

              <InnerPanel>
                <SubsectionHeader
                  title="分析摘要"
                  description={ANALYSIS_METHODS[run.method_name]?.description}
                />
                <InformationGrid
                  items={[
                    {
                      label: "分析方法",
                      value: ANALYSIS_METHODS[run.method_name]?.label || "舊版分析方法",
                    },
                    {
                      label: "捕捉紀錄",
                      value: run.record_id || "尚無資料",
                      truncate: true,
                    },
                    {
                      label: "建立時間",
                      value: formatDateTime(run.created_at),
                    },
                    {
                      label: "模型後端",
                      value: RECONSTRUCTION_BACKEND_LABELS[
                        run.reconstruction_backend
                      ] || "不建立模型",
                    },
                    {
                      label: "模型後端版本",
                      value: run.reconstruction_backend_version
                        || "尚無資料",
                    },
                    {
                      label: "平均重投影誤差",
                      value: displayNumber(
                        run.average_reprojection_error_px,
                        " px",
                        3,
                      ),
                    },
                    {
                      label: "模式數量",
                      value: `${quality.mode_count || modes.length} 種`,
                    },
                    {
                      label: "軌跡點數",
                      value: `${quality.point_count || trajectory.length} 點`,
                    },
                    {
                      label: "人工修正",
                      value: `${corrections.length} 筆`,
                    },
                    {
                      label: "座標空間",
                      value: "ArUco 世界座標（mm）",
                    },
                  ]}
                  rows={2}
                  minimumColumnWidth
                  scroll
                />
              </InnerPanel>

              <FormalTrajectoryViewer3D trajectory={trajectory} />

              <FormalTrajectoryCharts trajectory={trajectory} />

              <TrajectoryViewerModelOutputs
                analysisId={analysisId}
                models={models}
              />

              <InnerPanel>
                <SubsectionHeader
                  title="各模式運動摘要"
                  description="不同捕捉模式保持獨立，不會跨模式連接或插值。"
                />
                <div className="grid gap-3 min-[900px]:grid-cols-2">
                  {modes.map(([modeId, item]) => (
                    <div
                      className="grid gap-3 rounded-xl border border-white/15 bg-black/15 p-3"
                      key={modeId}
                    >
                      <div className="flex min-w-0 items-center justify-between gap-2">
                        <h4 className="m-0 truncate text-sm font-black text-white">
                          {modeId}
                        </h4>
                        <StatusPill tone={item.missing_point_count ? "warning" : "success"}>
                          {item.valid_point_count || 0} / {item.point_count || 0} 點
                        </StatusPill>
                      </div>
                      <InformationGrid
                        items={[
                          {
                            label: "三維位移",
                            value: displayNumber(item.net_displacement_mm, " mm", 3),
                          },
                          {
                            label: "路徑長度",
                            value: displayNumber(item.path_length_mm, " mm", 3),
                          },
                          {
                            label: "水平位移",
                            value: displayNumber(item.horizontal_displacement_mm, " mm", 3),
                          },
                          {
                            label: "垂直生長量",
                            value: displayNumber(item.vertical_growth_mm, " mm", 3),
                          },
                          {
                            label: "平均速度",
                            value: displayNumber(item.mean_speed_mm_per_second, " mm/s", 3),
                          },
                          {
                            label: "平均加速度",
                            value: displayNumber(item.mean_acceleration_mm_per_second2, " mm/s²", 3),
                          },
                          {
                            label: "旋轉方向",
                            value: (
                              TRAJECTORY_ROTATION_LABELS[
                                item.rotation_direction
                              ]
                              || "尚無資料"
                            ),
                          },
                          {
                            label: "Nutation 半徑",
                            value: displayNumber(item.nutation_radius_mm, " mm", 3),
                          },
                          {
                            label: "Nutation 週期",
                            value: displayNumber(item.nutation_period_seconds, " s", 2),
                          },
                          {
                            label: "缺失區段",
                            value: `${item.missing_segment_count || 0} 段`,
                          },
                          {
                            label: "插值點",
                            value: `${item.interpolated_point_count || 0} 點`,
                          },
                          {
                            label: "可用比例",
                            value: displayNumber(
                              item.usable_point_ratio * 100,
                              "%",
                              1,
                            ),
                          },
                        ]}
                        rows={2}
                        minimumColumnWidth
                        scroll
                      />
                    </div>
                  ))}
                </div>
              </InnerPanel>

              <InnerPanel>
                <SubsectionHeader
                  title="Round 結果"
                  description="列出每輪模型、尖端標記、來源、信心與重投影品質。"
                />
                <div className="max-h-[34rem] overflow-auto rounded-xl border border-white/15">
                  <div className="grid min-w-[72rem] grid-cols-[1.2fr_0.8fr_0.8fr_0.8fr_0.9fr_1.2fr_0.8fr_1fr] gap-3 border-b border-white/15 bg-white/7 px-3 py-2 text-xs font-black text-neutral-300">
                    <span>模式</span>
                    <span>Round</span>
                    <span>模型</span>
                    <span>尖端標記</span>
                    <span>信心</span>
                    <span>三維位置</span>
                    <span>誤差</span>
                    <span>來源</span>
                  </div>
                  {rounds.map((item) => {
                    const model = modelsByRound.get(item.round_key);
                    const landmark = resolved.get(item.round_key);
                    const modelStatus = ANALYSIS_MODEL_STATUS_META[
                      model?.status
                    ] || {
                      label: "無模型",
                      tone: "neutral",
                    };
                    return (
                      <div
                        className="grid min-w-[72rem] grid-cols-[1.2fr_0.8fr_0.8fr_0.8fr_0.9fr_1.2fr_0.8fr_1fr] items-center gap-3 border-b border-white/10 px-3 py-2 text-xs font-semibold text-neutral-300 last:border-b-0"
                        key={item.round_key}
                      >
                        <span className="truncate font-black text-white">
                          {item.mode_id}
                        </span>
                        <span>{item.round_id}</span>
                        <StatusPill tone={modelStatus.tone}>
                          {modelStatus.label}
                        </StatusPill>
                        <StatusPill tone={landmark?.valid ? "success" : "offline"}>
                          {landmark?.valid ? "有效" : "無效"}
                        </StatusPill>
                        <span>{displayNumber(landmark?.confidence * 100, "%", 1)}</span>
                        <span className="truncate">
                          {landmark?.valid
                            ? `${displayNumber(landmark.x_mm, "", 2)}, ${displayNumber(landmark.y_mm, "", 2)}, ${displayNumber(landmark.z_mm, " mm", 2)}`
                            : "尚無資料"
                          }
                        </span>
                        <span>{displayNumber(landmark?.mean_reprojection_error_px, " px", 3)}</span>
                        <span className="truncate">
                          {
                            TRAJECTORY_DETECTION_LABELS[
                              landmark?.detection_type
                            ]
                            || "尚無資料"
                          }
                        </span>
                      </div>
                    );
                  })}
                </div>
              </InnerPanel>
            </>
          ) : null}
        </div>
      </Panel>
    </div>
  );
}

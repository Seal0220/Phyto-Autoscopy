import InformationGrid from "@/components/data/InformationGrid";
import { StatusPill } from "@/components/panels/Panel";

import { ANALYSIS_CAMERA_LABELS } from "../analysisConfig";

const POSE_SOURCE_LABELS = {
  aruco: "ArUco",
  feature_refined: "特徵精修",
  motor_prior: "馬達先驗",
  interpolated: "相鄰姿態插值",
  invalid: "未解",
};

function count(value) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? Math.max(0, parsed) : 0;
}

function decimalLabel(
  value,
  unit,
  digits = 3,
) {
  const parsed = Number(value);
  return Number.isFinite(parsed)
    ? `${parsed.toFixed(digits)} ${unit}`
    : "尚無資料";
}

function mean(values) {
  const valid = values
    .map(Number)
    .filter(Number.isFinite);
  if (valid.length === 0) return null;
  return valid.reduce((total, value) => total + value, 0) / valid.length;
}

function AnalysisPoseRow({
  pose,
}) {
  const warnings = Array.isArray(pose.quality_warnings)
    ? pose.quality_warnings
    : [];
  const messages = [
    pose.failure_reason,
    ...warnings,
  ].filter(Boolean);

  return (
    <li className="grid min-w-0 gap-2 border-b border-white/15 py-3 last:border-b-0">
      <div className="flex min-w-0 flex-wrap items-center gap-2">
        <span className="text-xs font-black text-neutral-200">
          {ANALYSIS_CAMERA_LABELS[pose.camera_id]
            || pose.camera_id
            || "未知相機"
          }
        </span>
        <StatusPill tone={pose.valid ? "success" : "offline"}>
          {POSE_SOURCE_LABELS[pose.pose_source] || "未知來源"}
        </StatusPill>
        <span className="min-w-0 break-all text-xs font-semibold text-neutral-400">
          {pose.view_id || "未知 View"}
        </span>
      </div>

      <InformationGrid
        items={[
          {
            label: "可見標籤",
            value: `${Array.isArray(pose.detected_marker_ids)
              ? pose.detected_marker_ids.length
              : 0
            } 個`,
          },
          {
            label: "偵測角點",
            value: `${count(pose.detected_corner_count)} 個`,
          },
          {
            label: "ArUco 誤差",
            value: decimalLabel(
              pose.aruco_reprojection_error_px,
              "px",
            ),
          },
          {
            label: "精修誤差",
            value: decimalLabel(
              pose.refinement_reprojection_error_px,
              "px",
            ),
          },
          {
            label: "固定位置偏差",
            value: decimalLabel(
              pose.fixed_pose_translation_deviation_mm,
              "mm",
            ),
          },
          {
            label: "固定角度偏差",
            value: decimalLabel(
              pose.fixed_pose_rotation_deviation_deg,
              "°",
            ),
          },
        ]}
        border="none"
        columns={3}
        scroll
      />

      {messages.length > 0 ? (
        <ul className="m-0 grid gap-1 pl-4 text-xs font-semibold text-amber-200">
          {messages.map((message) => (
            <li key={message}>
              {message}
            </li>
          ))}
        </ul>
      ) : null}
    </li>
  );
}

export default function AnalysisPoseQuality({
  poses = [],
  quality,
}) {
  const validPoses = poses.filter((pose) => pose.valid);
  const invalidPoses = poses.filter((pose) => !pose.valid);
  const warningPoses = poses.filter((pose) => (
    Boolean(pose.failure_reason)
    || (
      Array.isArray(pose.quality_warnings)
      && pose.quality_warnings.length > 0
    )
  ));
  const problemPoses = [...new Map(
    [...invalidPoses, ...warningPoses].map((pose) => [
      pose.view_id,
      pose,
    ]),
  ).values()];
  const fixedCameraConsistency = Object.entries(
    quality?.fixed_camera_consistency || {},
  );
  const bundleAdjustment = (
    Array.isArray(quality?.rounds)
      ? quality.rounds
      : []
  )
    .map((round) => round?.bundle_adjustment)
    .filter(Boolean);
  const bundleAdjustmentFailed = bundleAdjustment.some(
    (item) => item.status === "failed",
  );
  const bundleAdjustmentCompleted = bundleAdjustment.some(
    (item) => item.status === "completed",
  );
  if (
    poses.length === 0
    && fixedCameraConsistency.length === 0
    && bundleAdjustment.length === 0
  ) {
    return null;
  }

  const status = validPoses.length === 0
    ? {
      label: "失敗",
      tone: "offline",
    }
    : validPoses.length < poses.length
      ? {
        label: "部分成功",
        tone: "warning",
      }
      : {
        label: "成功",
        tone: "success",
      };
  const arucoPoseCount = poses.filter(
    (pose) => pose.pose_source === "aruco",
  ).length;
  const refinedPoseCount = poses.filter(
    (pose) => pose.pose_source === "feature_refined",
  ).length;

  return (
    <section
      className="grid gap-3 border-t border-white/15 pt-3"
      aria-label="相機姿態品質"
    >
      <div className="flex flex-wrap items-center gap-2">
        <h4 className="m-0 text-sm font-black text-neutral-200">
          相機姿態品質
        </h4>
        <StatusPill tone={status.tone}>
          ArUco 對齊：{status.label}
        </StatusPill>
      </div>

      <InformationGrid
        items={[
          {
            label: "已定位影像",
            value: `${validPoses.length} / ${poses.length}`,
            tone: invalidPoses.length > 0 ? "warning" : "success",
          },
          {
            label: "平均 ArUco 誤差",
            value: decimalLabel(
              mean(poses.map(
                (pose) => pose.aruco_reprojection_error_px,
              )),
              "px",
            ),
          },
          {
            label: "ArUco 直接姿態",
            value: `${arucoPoseCount} 張`,
          },
          {
            label: "特徵精修姿態",
            value: `${refinedPoseCount} 張`,
          },
        ]}
        columns={4}
        scroll
      />

      {fixedCameraConsistency.map(([cameraId, summary]) => (
        <div
          className="grid gap-2 border-t border-white/15 pt-3"
          key={cameraId}
        >
          <div className="flex flex-wrap items-center gap-2">
            <h5 className="m-0 text-xs font-black text-neutral-300">
              {ANALYSIS_CAMERA_LABELS[cameraId] || cameraId}固定姿態
            </h5>
            <StatusPill
              tone={summary.status === "stable"
                ? "success"
                : summary.status === "warning"
                  ? "warning"
                  : "neutral"
              }
            >
              {summary.status === "stable"
                ? "穩定"
                : summary.status === "warning"
                  ? "可能位移"
                  : "尚無資料"
              }
            </StatusPill>
          </div>
          <InformationGrid
            items={[
              {
                label: "有效姿態",
                value: `${count(summary.valid_pose_count)} 張`,
              },
              {
                label: "最大位置偏差",
                value: decimalLabel(
                  summary.maximum_translation_deviation_mm,
                  "mm",
                ),
              },
              {
                label: "最大角度偏差",
                value: decimalLabel(
                  summary.maximum_rotation_deviation_deg,
                  "°",
                ),
              },
              {
                label: "警告影像",
                value: `${Array.isArray(summary.warning_view_ids)
                  ? summary.warning_view_ids.length
                  : 0
                } 張`,
                tone: summary.status === "warning"
                  ? "warning"
                  : "success",
              },
            ]}
            border="none"
            columns={4}
            scroll
          />
        </div>
      ))}

      {bundleAdjustment.length > 0 ? (
        <div className="grid gap-2 border-t border-white/15 pt-3">
          <div className="flex flex-wrap items-center gap-2">
            <h5 className="m-0 text-xs font-black text-neutral-300">
              受約束多視角姿態精修
            </h5>
            <StatusPill
              tone={bundleAdjustmentFailed
                ? "warning"
                : bundleAdjustmentCompleted
                  ? "success"
                  : "neutral"
              }
            >
              {bundleAdjustmentFailed
                ? "部分輪次使用原始姿態"
                : bundleAdjustmentCompleted
                  ? "精修完成"
                  : "未啟用"
              }
            </StatusPill>
          </div>
          <InformationGrid
            items={[
              {
                label: "完成輪次",
                value: `${bundleAdjustment.filter(
                  (item) => item.status === "completed",
                ).length} 輪`,
              },
              {
                label: "回退輪次",
                value: `${bundleAdjustment.filter(
                  (item) => item.status === "failed",
                ).length} 輪`,
                tone: bundleAdjustmentFailed
                  ? "warning"
                  : "success",
              },
              {
                label: "平均最終誤差",
                value: decimalLabel(
                  mean(bundleAdjustment.map(
                    (item) => item.final_reprojection_error_px,
                  )),
                  "px",
                ),
              },
              {
                label: "最大位置變化",
                value: decimalLabel(
                  Math.max(
                    ...bundleAdjustment.map((item) => (
                      Number(
                        item.maximum_translation_change_mm,
                      ) || 0
                    )),
                  ),
                  "mm",
                ),
              },
              {
                label: "最大角度變化",
                value: decimalLabel(
                  Math.max(
                    ...bundleAdjustment.map((item) => (
                      Number(item.maximum_rotation_change_deg) || 0
                    )),
                  ),
                  "°",
                ),
              },
            ]}
            border="none"
            columns={5}
            scroll
          />
        </div>
      ) : null}

      {problemPoses.length > 0 ? (
        <details className="group border-t border-white/15 pt-3">
          <summary className="cursor-pointer text-sm font-black text-neutral-300 transition-colors duration-200 hover:text-white">
            失敗與警告影像（{problemPoses.length} 張）
          </summary>
          <ul className="mt-2 mb-0 max-h-80 list-none overflow-y-auto overscroll-contain border-y border-white/15 px-1">
            {problemPoses.map((pose) => (
              <AnalysisPoseRow
                key={pose.view_id}
                pose={pose}
              />
            ))}
          </ul>
          <p className="mt-2 mb-0 text-xs font-semibold text-neutral-500">
            完整逐影像姿態與品質保存在 camera_poses.json。
          </p>
        </details>
      ) : null}
    </section>
  );
}

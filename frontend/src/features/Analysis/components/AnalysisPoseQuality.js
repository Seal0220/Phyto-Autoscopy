import { StatusPill } from "@/components/panels/Panel";

const ALIGNMENT_STATUS = {
  success: {
    label: "成功",
    tone: "success",
  },
  partial: {
    label: "部分成功",
    tone: "warning",
  },
  failed: {
    label: "失敗",
    tone: "offline",
  },
};

const CAMERA_LABELS = {
  top: "俯視角",
  side: "側視角",
  rotating: "旋臂視角",
};

const POSE_SOURCE_LABELS = {
  aruco: "ArUco",
  aruco_refined: "ArUco 穩定解",
  sfm: "SfM 補齊",
  motor_prior: "馬達角度先驗",
  unresolved: "未解",
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

function percentageLabel(value) {
  const parsed = Number(value);
  return Number.isFinite(parsed)
    ? `${(parsed * 100).toFixed(1)}%`
    : "尚無資料";
}

function Metric({
  label,
  value,
}) {
  return (
    <div className="min-w-0">
      <dt className="text-xs font-black text-neutral-500">
        {label}
      </dt>
      <dd className="mt-1 m-0 break-words font-bold text-neutral-200">
        {value}
      </dd>
    </div>
  );
}

function PoseSummary({
  title,
  metrics,
}) {
  if (!metrics || Object.keys(metrics).length === 0) return null;

  return (
    <div className="grid gap-2 border-t border-white/15 pt-3">
      <h5 className="m-0 text-xs font-black text-neutral-300">
        {title}
      </h5>
      <dl className="grid min-w-0 gap-3 text-sm min-[520px]:grid-cols-2 min-[900px]:grid-cols-4">
        {metrics.map((metric) => (
          <Metric
            key={metric.label}
            label={metric.label}
            value={metric.value}
          />
        ))}
      </dl>
    </div>
  );
}

function PoseRow({ pose }) {
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
          {CAMERA_LABELS[pose.camera_id] || pose.camera_id || "未知相機"}
        </span>
        <StatusPill tone={pose.resolved ? "success" : "offline"}>
          {POSE_SOURCE_LABELS[pose.source] || pose.source || "未解"}
        </StatusPill>
        <span className="min-w-0 break-all text-xs font-semibold text-neutral-400">
          {pose.relative_path || `影像 ${pose.input_id ?? "—"}`}
        </span>
      </div>

      <dl className="grid min-w-0 gap-2 text-xs min-[520px]:grid-cols-4">
        <Metric
          label="可見標籤"
          value={`${count(pose.visible_marker_count)} 個`}
        />
        <Metric
          label="PnP 內點"
          value={`${count(pose.pnp_inlier_count)} 個`}
        />
        <Metric
          label="ArUco 誤差"
          value={decimalLabel(pose.aruco_reprojection_error_px, "px")}
        />
        <Metric
          label="SfM 配對"
          value={`${count(pose.sfm_match_count)} 組`}
        />
      </dl>

      {messages.length ? (
        <ul className="m-0 grid gap-1 pl-4 text-xs font-semibold text-amber-200">
          {messages.map((message, index) => (
            <li key={`${message}-${index}`}>
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
  if (!quality || Object.keys(quality).length === 0) return null;

  const status = ALIGNMENT_STATUS[quality.status]
    || {
      label: "尚未完成",
      tone: "neutral",
    };
  const fixedCameraSummaries = Object.entries(
    quality.fixed_camera_dispersion || {},
  );
  const continuity = quality.rotating_pose_continuity || {};
  const motorConsistency = quality.motor_trajectory_consistency || {};
  const hasRotatingPoses = poses.some((pose) => (
    pose.camera_id === "rotating"
  ));
  const problemPoses = poses.filter((pose) => (
    !pose.resolved
    || Boolean(pose.failure_reason)
    || (Array.isArray(pose.quality_warnings)
      && pose.quality_warnings.length > 0)
  ));

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

      <dl className="grid min-w-0 gap-3 text-sm min-[520px]:grid-cols-2 min-[900px]:grid-cols-5">
        <Metric
          label="已定位影像"
          value={`${count(quality.resolved_image_count)} / ${count(quality.total_image_count)}`}
        />
        <Metric
          label="平均 ArUco 重投影誤差"
          value={decimalLabel(
            quality.average_aruco_reprojection_error_px,
            "px",
          )}
        />
        <Metric
          label="SfM 補齊影像"
          value={`${count(quality.sfm_image_count)} 張`}
        />
        <Metric
          label="SfM 註冊率"
          value={`${count(quality.sfm_registered_image_count)} 張／${percentageLabel(quality.sfm_registration_rate)}`}
        />
        <Metric
          label="未解影像"
          value={`${count(quality.unresolved_image_count)} 張`}
        />
      </dl>

      {fixedCameraSummaries.map(([cameraId, dispersion]) => (
        <PoseSummary
          key={cameraId}
          title={`${CAMERA_LABELS[cameraId] || cameraId}固定姿態離散程度`}
          metrics={[
            {
              label: "採用樣本",
              value: `${count(dispersion.accepted_sample_count)} / ${count(dispersion.sample_count)}`,
            },
            {
              label: "平移中位數",
              value: decimalLabel(dispersion.translation_median_mm, "mm"),
            },
            {
              label: "平移最大值",
              value: decimalLabel(dispersion.translation_maximum_mm, "mm"),
            },
            {
              label: "旋轉最大值",
              value: decimalLabel(dispersion.rotation_maximum_deg, "°"),
            },
          ]}
        />
      ))}

      {hasRotatingPoses ? (
        <>
          <PoseSummary
            title="旋臂姿態連續性"
            metrics={[
              {
                label: "已定位影像",
                value: `${count(continuity.resolved_count)} 張`,
              },
              {
                label: "平移步長中位數",
                value: decimalLabel(
                  continuity.translation_step_median_mm,
                  "mm",
                ),
              },
              {
                label: "旋轉步長中位數",
                value: decimalLabel(
                  continuity.rotation_step_median_deg,
                  "°",
                ),
              },
              {
                label: "旋轉步長最大值",
                value: decimalLabel(
                  continuity.rotation_step_maximum_deg,
                  "°",
                ),
              },
            ]}
          />

          <PoseSummary
            title="馬達角度與相機軌跡一致性"
            metrics={[
              {
                label: "可比較步數",
                value: `${count(motorConsistency.comparable_step_count)} 步`,
              },
              {
                label: "差異中位數",
                value: decimalLabel(
                  motorConsistency.rotation_to_motor_delta_median_deg,
                  "°",
                ),
              },
              {
                label: "最大差異",
                value: decimalLabel(
                  motorConsistency.rotation_to_motor_delta_maximum_deg,
                  "°",
                ),
              },
            ]}
          />
        </>
      ) : null}

      {problemPoses.length ? (
        <details className="group border-t border-white/15 pt-3">
          <summary className="cursor-pointer text-sm font-black text-neutral-300 transition-colors duration-200 hover:text-white">
            失敗與警告影像（{problemPoses.length} 張）
          </summary>
          <ul className="mt-2 mb-0 max-h-80 list-none overflow-y-auto overscroll-contain border-y border-white/15 px-1">
            {problemPoses.map((pose, index) => (
              <PoseRow
                key={`${pose.camera_id}-${pose.input_id}-${index}`}
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

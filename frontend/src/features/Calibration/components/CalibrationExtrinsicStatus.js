import { FiRefreshCw } from "react-icons/fi";

import Button from "@/components/buttons/Button";
import StatusCard from "@/components/cards/StatusCard";
import SubsectionHeader from "@/components/headers/SubsectionHeader";
import { formatDateTime } from "@/lib/formatUtils";

const QUALITY_LABELS = {
  excellent: "優良",
  acceptable: "通過",
  warning: "需檢查",
  failed: "未通過",
};

export default function CalibrationExtrinsicStatus({
  status,
  locked,
  pendingAction,
  onAction,
}) {
  const activeProfile = status?.active_extrinsic;

  return (
    <section
      className="grid gap-3"
      aria-labelledby="calibration-extrinsic-status-title"
    >
      <SubsectionHeader
        titleId="calibration-extrinsic-status-title"
        title="外參狀態"
        description="確認目前外參校正檔、旋臂幾何與校正資料儲存狀態。"
      >
        {status?.storage_synchronized === false ? (
          <Button
            disabled={!locked || Boolean(pendingAction)}
            onClick={() => void onAction(
              "storage.reconcile",
              "/api/calibration/storage/reconcile",
              {
                successMessage: "校正檔案已重新同步。",
              },
            )}
          >
            <FiRefreshCw
              className="size-4 shrink-0"
              aria-hidden="true"
            />
            重新同步校正檔
          </Button>
        ) : null}
      </SubsectionHeader>

      <div className="grid gap-3 min-[520px]:grid-cols-5 min-[900px]:grid-cols-5">
        <StatusCard
          title="目前外參"
          content={activeProfile?.name || "尚未啟用"}
          note={activeProfile?.profile_id || "無啟用校正檔"}
          className="[&>div:first-of-type]:break-all [&>div:first-of-type]:text-lg"
        />
        <StatusCard
          title="外參品質"
          content={QUALITY_LABELS[activeProfile?.quality_status] || "—"}
          note={activeProfile?.status || "尚無資料"}
        />
        <StatusCard
          title="旋臂狀態"
          content={`${Number(status?.motor_angle_deg || 0).toFixed(1)}°`}
          note={status?.arm_height_mm === null || status?.arm_height_mm === undefined
            ? "高度尚未設定"
            : `高度 ${Number(status.arm_height_mm).toFixed(1)} mm`
          }
        />
        <StatusCard
          title="最近校正"
          content={formatDateTime(status?.latest_calibration_at)}
          note={status?.recent_error || "目前沒有錯誤"}
          className="[&>div:first-of-type]:text-base"
        />
        <StatusCard
          title="校正儲存"
          content={status?.storage_synchronized === false ? "待修復" : "已同步"}
          note={status?.storage_error || "data/calibration"}
          className="[&>div:first-of-type]:text-lg [&>div:last-of-type]:break-all"
        />
      </div>
    </section>
  );
}

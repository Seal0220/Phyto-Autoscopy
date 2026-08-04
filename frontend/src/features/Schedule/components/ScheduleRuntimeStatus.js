"use client";

import StatusCard from "@/components/cards/StatusCard";
import { Panel, PanelHeader } from "@/components/panels/Panel";
import useElapsedSeconds from "@/hooks/useElapsedSeconds";
import { formatElapsed } from "@/lib/formatUtils";

import {
  scheduleErrorMessage,
  scheduleStatusLabel,
} from "../lib/scheduleUtils";

export default function ScheduleRuntimeStatus({
  scheduleStatus,
  motor,
  schedule,
}) {
  const status = scheduleStatus.status || "idle";
  const elapsedSeconds = useElapsedSeconds({
    elapsedSeconds: scheduleStatus.elapsed_seconds,
    resetKey: scheduleStatus.record_id,
    status,
  });
  const cycleElapsedSeconds = useElapsedSeconds({
    elapsedSeconds: scheduleStatus.cycle_elapsed_seconds,
    resetKey: `${scheduleStatus.record_id || "idle"}:${scheduleStatus.cycle_count || 0}`,
    status: scheduleStatus.cycle_active
      ? status
      : "idle",
  });
  const totalDuration = formatElapsed(
    scheduleStatus.duration_seconds ?? Number(schedule.duration_seconds || 0),
  );
  const cycleElapsed = formatElapsed(
    cycleElapsedSeconds,
  );
  const hasRuntimePlan = [
    "running",
    "paused",
    "stopping",
    "failed",
  ].includes(status);
  const rotationEnabled = hasRuntimePlan
    ? Boolean(scheduleStatus.rotation_enabled)
    : Boolean(schedule.rotation_enabled);
  const totalCycles = hasRuntimePlan
    ? Number(scheduleStatus.total_cycles || 0)
    : Number(schedule.total_cycles || 0);
  const angle = Number(
    motor.command_position_deg ?? scheduleStatus.current_angle_deg,
  );
  const currentAngle = Number.isFinite(angle)
    ? angle.toFixed(3).replace(/\.?0+$/, "")
    : "—";

  return (
    <Panel
      id="runtime-status"
      className="min-[981px]:col-start-1 min-[981px]:row-start-2 scroll-mt-[8.75rem] max-[980px]:scroll-mt-[11.5rem]"
      aria-label="運行狀態"
    >
      <PanelHeader title="運行狀態" />
      <section
        className="grid grid-cols-1 gap-2 p-5 min-[520px]:grid-cols-2 min-[900px]:grid-cols-4 max-sm:p-4"
        aria-label="排程運行狀態"
        role={status === "failed" ? "alert" : "status"}
        aria-live="polite"
      >
        <StatusCard
          title="排程狀態"
          content={scheduleStatusLabel(status)}
          note={status === "failed" ? scheduleErrorMessage(scheduleStatus.last_error) : ""}
        />
        <StatusCard
          title="排程執行時間"
          content={formatElapsed(elapsedSeconds)}
          note={rotationEnabled
            ? ""
            : `/ 共 ${totalDuration}`
          }
        />
        <StatusCard
          title="排程"
          content={rotationEnabled
            ? `${scheduleStatus.cycle_count ?? 0} / ${totalCycles}`
            : "三鏡頭"
          }
          note={rotationEnabled
            ? `本輪耗時 ${cycleElapsed}`
            : "時間擷取"
          }
        />
        <StatusCard
          title="目前角度"
          content={rotationEnabled ? currentAngle : "—"}
          note={rotationEnabled ? "度" : "未啟用旋臂"}
        />
      </section>
    </Panel>
  );
}

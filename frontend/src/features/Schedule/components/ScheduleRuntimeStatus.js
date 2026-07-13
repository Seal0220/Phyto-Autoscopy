"use client";

import StatusCard from "@/components/cards/StatusCard";
import { Panel, PanelHeader } from "@/components/panels/Panel";
import useElapsedSeconds from "@/hooks/useElapsedSeconds";
import { formatElapsed } from "@/lib/formatUtils";

import { SCHEDULE_STATUS_LABELS } from "../scheduleConfig";

export default function ScheduleRuntimeStatus({
  experiment,
  motor,
  schedule,
}) {
  const status = experiment.status || "idle";
  const elapsedSeconds = useElapsedSeconds({
    elapsedSeconds: experiment.elapsed_seconds,
    status,
  });
  const totalDuration = formatElapsed(
    experiment.duration_seconds ?? Number(schedule.duration_seconds || 0),
  );
  const angle = Number(
    motor.command_position_deg ?? experiment.current_angle_deg,
  );
  const currentAngle = Number.isFinite(angle)
    ? angle.toFixed(3).replace(/\.?0+$/, "")
    : "—";

  return (
    <Panel
      id="runtime-status"
      className="min-[981px]:col-start-1 min-[981px]:row-start-2 scroll-mt-[5.6rem] max-[980px]:scroll-mt-[8.8rem]"
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
          content={SCHEDULE_STATUS_LABELS[status] || status}
          note=""
        />
        <StatusCard
          title="排程執行時間"
          content={formatElapsed(elapsedSeconds)}
          note={`/ 共 ${totalDuration}`}
        />
        <StatusCard
          title="排程"
          content={experiment.cycle_count ?? 0}
          note="次循環"
        />
        <StatusCard
          title="目前角度"
          content={currentAngle}
          note="度"
        />
      </section>
    </Panel>
  );
}

"use client";

import StatusCard from "@/components/cards/StatusCard";
import useElapsedSeconds from "@/hooks/useElapsedSeconds";
import { formatElapsed } from "@/lib/formatUtils";

import { SCHEDULE_STATUS_LABELS } from "../scheduleConfig";

export default function ScheduleStatusCards({
  experiment,
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

  return (
    <section
      className="grid grid-cols-1 gap-2 min-[520px]:grid-cols-3"
      aria-label="排程執行狀態"
      role={status === "failed" ? "alert" : "status"}
      aria-live="polite"
    >
      <StatusCard
        title="排程狀態"
        content={SCHEDULE_STATUS_LABELS[status] || status}
        note=""
      />
      <StatusCard
        title="執行時間"
        content={formatElapsed(elapsedSeconds)}
        note={`/ 共 ${totalDuration}`}
      />
      <StatusCard
        title="循環進度"
        content={experiment.cycle_count ?? 0}
        note="次循環"
      />
    </section>
  );
}

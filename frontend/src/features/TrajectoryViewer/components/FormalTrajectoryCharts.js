"use client";

import { useState } from "react";

import SubsectionHeader from "@/components/headers/SubsectionHeader";
import InnerPanel from "@/components/panels/InnerPanel";

import { formalTrajectoryModeColors } from "../lib/trajectoryUtils";
import { TRAJECTORY_METRICS } from "../trajectoryViewerConfig";
import FormalTrajectoryMetricChart from "./FormalTrajectoryMetricChart";

export default function FormalTrajectoryCharts({
  trajectory,
}) {
  const [selectedMetricKey, setSelectedMetricKey] = useState(TRAJECTORY_METRICS[0].key);
  const selectedMetric = TRAJECTORY_METRICS.find(
    (metric) => metric.key === selectedMetricKey,
  ) || TRAJECTORY_METRICS[0];
  const colorByMode = formalTrajectoryModeColors(trajectory);

  return (
    <InnerPanel>
      <SubsectionHeader
        title="高度時間軸"
        description="時間以日、時、分、秒、毫秒顯示，下方保留秒數；各模式獨立，缺失輪次不連線。"
      />
      <div
        className="flex flex-wrap gap-2"
        role="group"
        aria-label="軌跡圖表指標"
      >
        {TRAJECTORY_METRICS.map((metric) => (
          <button
            type="button"
            key={metric.key}
            aria-pressed={selectedMetric.key === metric.key}
            onClick={() => setSelectedMetricKey(metric.key)}
            className={`cursor-pointer rounded-lg border px-3 py-2 text-xs font-bold transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-300 ${
              selectedMetric.key === metric.key
                ? "border-emerald-300/60 bg-emerald-500/20 text-emerald-100"
                : "border-white/15 bg-black/15 text-neutral-300 hover:border-emerald-300/40 hover:text-white"
            }`}
          >
            {metric.label}
          </button>
        ))}
      </div>
      <FormalTrajectoryMetricChart
        colorByMode={colorByMode}
        metric={selectedMetric}
        trajectory={trajectory}
      />
      <div className="flex flex-wrap gap-3 text-xs font-semibold text-neutral-400">
        {Object.entries(colorByMode).map(([modeId, color]) => (
          <span key={modeId}>
            <i
              className="mr-1 inline-block size-2 rounded-full"
              style={{
                backgroundColor: color,
              }}
            />
            {modeId}
          </span>
        ))}
        <span>
          <i className="mr-1 inline-block size-2 rounded-full bg-white" />
          人工修正
        </span>
      </div>
    </InnerPanel>
  );
}

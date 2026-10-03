"use client";

import { useState } from "react";

import SubsectionHeader from "@/components/headers/SubsectionHeader";
import InnerPanel from "@/components/panels/InnerPanel";

import { formalTrajectoryModeColors } from "../lib/trajectoryUtils";

const CHART_WIDTH = 720;
const CHART_HEIGHT = 260;
const PADDING = {
  top: 18,
  right: 20,
  bottom: 42,
  left: 66,
};
const GRID_STEPS = [0, 0.25, 0.5, 0.75, 1];

const METRICS = [
  {
    key: "z_mm",
    label: "尖端高度",
    unit: "mm",
    digits: 2,
  },
  {
    key: "horizontal_displacement_mm",
    label: "水平位移",
    unit: "mm",
    digits: 2,
  },
  {
    key: "speed_mm_per_second",
    label: "移動速度",
    unit: "mm/s",
    digits: 3,
  },
  {
    key: "confidence",
    label: "尖端標記信心",
    unit: "%",
    digits: 1,
    transform: (value) => value * 100,
  },
];

function finiteNumber(value) {
  if (value === null || value === undefined || value === "") return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function valueBounds(values) {
  const minimum = Math.min(...values);
  const maximum = Math.max(...values);
  if (minimum === maximum) {
    const padding = Math.max(Math.abs(minimum) * 0.05, 1);
    return {
      minimum: minimum - padding,
      maximum: maximum + padding,
      span: padding * 2,
    };
  }
  const padding = (maximum - minimum) * 0.08;
  return {
    minimum: minimum - padding,
    maximum: maximum + padding,
    span: maximum - minimum + padding * 2,
  };
}

function metricSeries(
  trajectory,
  metric,
) {
  const transform = metric.transform || ((value) => value);
  const modes = [...new Set(
    trajectory.map((item) => item.mode_id).filter(Boolean),
  )];
  const series = [];

  for (const modeId of modes) {
    const points = trajectory
      .filter((item) => item.mode_id === modeId)
      .sort((left, right) => left.point_index - right.point_index);
    let segment = [];

    for (const point of points) {
      const rawValue = finiteNumber(point[metric.key]);
      const xValue = finiteNumber(point.elapsed_seconds)
        ?? finiteNumber(point.point_index);
      if (
        !point.valid
        || rawValue === null
        || xValue === null
      ) {
        if (segment.length) series.push({ modeId, points: segment });
        segment = [];
        continue;
      }
      if (point.missing_segment && segment.length) {
        series.push({
          modeId,
          points: segment,
        });
        segment = [];
      }
      segment.push({
        ...point,
        chartX: xValue,
        chartY: transform(rawValue),
      });
    }
    if (segment.length) series.push({ modeId, points: segment });
  }

  return series;
}

function formatValue(
  value,
  digits,
) {
  return Number(value).toFixed(digits);
}

function MetricChart({
  colorByMode,
  metric,
  trajectory,
}) {
  const series = metricSeries(trajectory, metric);
  const points = series.flatMap((item) => item.points);

  if (!points.length) {
    return (
      <div className="grid min-h-72 place-items-center rounded-xl border border-dashed border-white/15 bg-black/15 p-5 text-center text-sm font-semibold text-neutral-400">
        {metric.label}尚無可顯示的有效資料。
      </div>
    );
  }

  const xBounds = valueBounds(points.map((point) => point.chartX));
  const yBounds = valueBounds(points.map((point) => point.chartY));
  const plotWidth = CHART_WIDTH - PADDING.left - PADDING.right;
  const plotHeight = CHART_HEIGHT - PADDING.top - PADDING.bottom;
  const projectX = (value) => PADDING.left
    + ((value - xBounds.minimum) / xBounds.span) * plotWidth;
  const projectY = (value) => PADDING.top
    + (1 - (value - yBounds.minimum) / yBounds.span) * plotHeight;

  return (
    <div className="grid min-w-0 gap-2 rounded-xl border border-white/15 bg-black/15 p-3">
      <div className="flex min-w-0 items-baseline justify-between gap-3">
        <h4 className="m-0 text-sm font-black text-white">
          {metric.label}
        </h4>
        <span className="text-xs font-bold text-neutral-500">
          {metric.unit}
        </span>
      </div>
      <div className="aspect-[18/7] min-w-0 overflow-hidden">
        <svg
          className="size-full"
          viewBox={`0 0 ${CHART_WIDTH} ${CHART_HEIGHT}`}
          role="img"
          aria-label={`${metric.label}跨輪變化圖`}
        >
          {GRID_STEPS.map((ratio) => {
            const y = PADDING.top + ratio * plotHeight;
            const value = yBounds.maximum - ratio * yBounds.span;
            return (
              <g key={`y-${ratio}`}>
                <line
                  x1={PADDING.left}
                  y1={y}
                  x2={CHART_WIDTH - PADDING.right}
                  y2={y}
                  stroke="rgba(255,255,255,0.10)"
                />
                <text
                  x={PADDING.left - 8}
                  y={y + 4}
                  fill="#a3a3a3"
                  fontSize="11"
                  fontWeight="700"
                  textAnchor="end"
                >
                  {formatValue(value, metric.digits)}
                </text>
              </g>
            );
          })}
          {GRID_STEPS.map((ratio) => {
            const x = PADDING.left + ratio * plotWidth;
            const value = xBounds.minimum + ratio * xBounds.span;
            return (
              <g key={`x-${ratio}`}>
                <line
                  x1={x}
                  y1={PADDING.top}
                  x2={x}
                  y2={CHART_HEIGHT - PADDING.bottom}
                  stroke="rgba(255,255,255,0.06)"
                />
                <text
                  x={x}
                  y={CHART_HEIGHT - 18}
                  fill="#a3a3a3"
                  fontSize="11"
                  fontWeight="700"
                  textAnchor="middle"
                >
                  {formatValue(value, 1)}
                </text>
              </g>
            );
          })}
          <text
            x={CHART_WIDTH / 2}
            y={CHART_HEIGHT - 2}
            fill="#737373"
            fontSize="11"
            fontWeight="700"
            textAnchor="middle"
          >
            經過時間（秒；無時間時使用輪次順序）
          </text>
          {series.map((item, index) => {
            const color = colorByMode[item.modeId] || "#6ee7b7";
            const projected = item.points.map((point) => ({
              ...point,
              plotX: projectX(point.chartX),
              plotY: projectY(point.chartY),
            }));
            const path = projected
              .map((point) => `${point.plotX},${point.plotY}`)
              .join(" ");

            return (
              <g key={`${item.modeId}-${index}`}>
                {projected.length > 1 ? (
                  <polyline
                    points={path}
                    fill="none"
                    stroke={color}
                    strokeWidth="3"
                    strokeLinejoin="round"
                    strokeLinecap="round"
                  />
                ) : null}
                {projected.map((point) => (
                  <circle
                    key={`${point.round_key}-${metric.key}`}
                    cx={point.plotX}
                    cy={point.plotY}
                    r={point.manually_corrected ? 5.5 : 4}
                    fill={point.manually_corrected ? "#ffffff" : color}
                    stroke={color}
                    strokeWidth={point.manually_corrected ? "3" : "1.5"}
                  >
                    <title>
                      {`${point.mode_id} / ${point.round_id}・${metric.label} ${formatValue(point.chartY, metric.digits)} ${metric.unit}`}
                    </title>
                  </circle>
                ))}
              </g>
            );
          })}
        </svg>
      </div>
    </div>
  );
}

export default function FormalTrajectoryCharts({
  trajectory,
}) {
  const [selectedMetricKey, setSelectedMetricKey] = useState(METRICS[0].key);
  const selectedMetric = METRICS.find(
    (metric) => metric.key === selectedMetricKey,
  ) || METRICS[0];
  const colorByMode = formalTrajectoryModeColors(trajectory);

  return (
    <InnerPanel>
      <SubsectionHeader
        title="跨輪運動圖表"
        description="切換指標查看同一張圖；各模式維持獨立系列，缺失輪次會中斷線段。"
      />
      <div className="flex flex-wrap gap-2" role="group" aria-label="軌跡圖表指標">
        {METRICS.map((metric) => (
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
      <MetricChart
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

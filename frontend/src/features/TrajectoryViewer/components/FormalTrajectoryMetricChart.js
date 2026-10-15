import { formatElapsedPrecise } from "@/lib/formatUtils";
import useTrajectoryChartSize from "../hooks/useTrajectoryChartSize";
import { trajectoryMetricBounds, trajectoryMetricSeries, trajectoryMetricTicks, trajectoryMetricTimeBounds } from "../lib/trajectoryMetricUtils";
import { TRAJECTORY_METRIC_CHART, TRAJECTORY_POINT_OUTLINE } from "../trajectoryViewerConfig";

export default function FormalTrajectoryMetricChart({
  colorByMode,
  metric,
  trajectory,
}) {
  const { series, hasTime } = trajectoryMetricSeries(trajectory, metric);
  const points = series.flatMap((item) => item.points);
  const { elementRef, width, height } = useTrajectoryChartSize({ enabled: points.length > 0 });
  if (!points.length) {
    return (
      <div className="grid min-h-72 place-items-center rounded-xl border border-dashed border-white/15 bg-black/15 p-5 text-center text-sm font-semibold text-neutral-400">
        {metric.label}尚無可顯示的有效資料。
      </div>
    );
  }
  const { padding, gridSteps, tickSize, secondsSize, axisTitleSize } = TRAJECTORY_METRIC_CHART;
  const xBounds = trajectoryMetricTimeBounds(points.map((point) => point.chartX), hasTime);
  const yBounds = trajectoryMetricBounds(points.map((point) => point.chartY));
  const plotWidth = width - padding.left - padding.right;
  const plotHeight = height - padding.top - padding.bottom;
  const plotBottom = height - padding.bottom;
  const projectX = (value) => padding.left + (value - xBounds.minimum) / xBounds.span * plotWidth;
  const projectY = (value) => padding.top + (1 - (value - yBounds.minimum) / yBounds.span) * plotHeight;

  return (
    <div className="grid min-w-0 gap-2 rounded-xl border border-white/15 bg-black/15 p-3">
      <div className="flex min-w-0 items-baseline justify-between gap-3">
        <h4 className="m-0 text-sm font-black text-white">{metric.label}</h4>
        <span className="text-xs font-bold text-neutral-500">{metric.unit}</span>
      </div>
      <div
        ref={elementRef}
        className="relative aspect-[18/7] min-h-72 w-full min-w-0 overflow-hidden"
      >
        <svg
          className="absolute inset-0 size-full"
          viewBox={`0 0 ${width} ${height}`}
          role="img"
          aria-label={`${metric.label}時間軸`}
        >
          {gridSteps.map((ratio) => {
            const y = padding.top + ratio * plotHeight;
            const value = yBounds.maximum - ratio * yBounds.span;
            return (
              <g
                key={`y-${ratio}`}
                data-axis="y"
              >
                <line
                  x1={padding.left}
                  y1={y}
                  x2={width - padding.right}
                  y2={y}
                  stroke="rgba(255,255,255,0.10)"
                />
                <text
                  x={padding.left - 8}
                  y={y + 3}
                  fill="#a3a3a3"
                  fontSize={tickSize}
                  fontWeight="600"
                  textAnchor="end"
                >
                  {value.toFixed(metric.digits)}
                </text>
              </g>
            );
          })}
          {trajectoryMetricTicks(plotWidth).map((ratio) => {
            const x = padding.left + ratio * plotWidth;
            const value = xBounds.minimum + ratio * xBounds.span;
            const formatted = hasTime ? formatElapsedPrecise(value).split(" ") : null;
            const textAnchor = ratio === 0 ? "start" : ratio === 1 ? "end" : "middle";
            return (
              <g
                key={`x-${ratio}`}
                data-axis="x"
              >
                <line
                  x1={x}
                  y1={padding.top}
                  x2={x}
                  y2={plotBottom}
                  stroke="rgba(255,255,255,0.06)"
                />
                <text
                  x={x}
                  y={plotBottom + 16}
                  fill="#a3a3a3"
                  fontSize={tickSize}
                  fontWeight="600"
                  textAnchor={textAnchor}
                >
                  {formatted ? (
                    <>
                      <tspan
                        x={x}
                        dy={0}
                      >
                        {formatted.slice(0, 3).join(" ")}
                      </tspan>
                      <tspan
                        x={x}
                        dy={13}
                      >
                        {formatted.slice(3).join(" ")}
                      </tspan>
                    </>
                  ) : value.toFixed(1)}
                </text>
                {hasTime ? (
                  <text
                    x={x}
                    y={plotBottom + 42}
                    fill="#737373"
                    fontSize={secondsSize}
                    fontWeight="500"
                    textAnchor={textAnchor}
                    data-time-seconds="true"
                  >
                    {value.toFixed(3)} 秒
                  </text>
                ) : null}
              </g>
            );
          })}
          <text
            x={padding.left + plotWidth / 2}
            y={height - 9}
            fill="#737373"
            fontSize={axisTitleSize}
            fontWeight="600"
            textAnchor="middle"
          >
            {hasTime ? "經過時間" : "輪次順序（缺少時間資料）"}
          </text>
          {series.map((item, index) => {
            const color = colorByMode[item.modeId] || "#6ee7b7";
            return (
              <g key={`${item.modeId}-${index}`}>
                {item.points.length > 1 ? (
                  <polyline
                    points={item.points.map((point) => `${projectX(point.chartX)},${projectY(point.chartY)}`).join(" ")}
                    fill="none"
                    stroke={color}
                    strokeWidth="3"
                    strokeLinejoin="round"
                    strokeLinecap="round"
                  />
                ) : null}
                {item.points.map((point) => (
                  <circle
                    key={`${point.round_key || `${point.mode_id}:${point.round_id}:${point.point_index}`}-${metric.key}`}
                    cx={projectX(point.chartX)}
                    cy={projectY(point.chartY)}
                    r={point.manually_corrected ? 5.5 : 4}
                    fill={point.manually_corrected ? "#ffffff" : color}
                    stroke={TRAJECTORY_POINT_OUTLINE.color}
                    strokeWidth={TRAJECTORY_POINT_OUTLINE.width}
                    vectorEffect="non-scaling-stroke"
                  >
                    <title>
                      {`${point.mode_id} / ${point.round_id}・${metric.label} ${point.chartY.toFixed(metric.digits)} ${metric.unit}${hasTime ? `・${formatElapsedPrecise(point.chartX)}（${point.chartX.toFixed(3)} 秒）` : ""}`}
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

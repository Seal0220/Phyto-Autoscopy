import StatusCard from "@/components/cards/StatusCard";
import InnerPanel from "@/components/panels/InnerPanel";
import SubsectionHeader from "@/components/headers/SubsectionHeader";

import {
  HIGH_REPROJECTION_ERROR_PX,
  isHighReprojectionError,
  reprojectionChartPoints,
  reprojectionHistogram,
  reprojectionStatistics,
} from "./lib/reprojectionUtils";

const CHART_WIDTH = 760;
const CHART_HEIGHT = 340;
const CHART_PADDING = 34;

function statisticValue(
  value,
  fallback,
) {
  if (value == null) return fallback;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function pointsAttribute(points) {
  return points.map((point) => `${point.plotX},${point.plotY}`).join(" ");
}

function errorPointTitle(point) {
  return [
    `影格 ${point.frameId}`,
    `俯視 ${point.top.toFixed(2)} px`,
    `側視 ${point.side.toFixed(2)} px`,
    ...(Number.isFinite(point.rotating)
      ? [`環繞 ${point.rotating.toFixed(2)} px`]
      : []),
    `整體 ${point.overall.toFixed(2)} px`,
  ].join(" · ");
}

export default function ReprojectionErrors({
  errors,
  summary,
}) {
  const calculated = reprojectionStatistics(errors);
  const backend = summary?.reprojection || {};
  const statistics = {
    topMean: statisticValue(backend.top_mean_px, calculated.topMean),
    sideMean: statisticValue(backend.side_mean_px, calculated.sideMean),
    overallMean: statisticValue(
      backend.overall_mean_px,
      calculated.overallMean,
    ),
    standardDeviation: statisticValue(
      backend.overall_std_px,
      calculated.standardDeviation,
    ),
    maximum: statisticValue(backend.maximum_error_px, calculated.maximum),
    highCount: calculated.highCount,
    highRatio: calculated.highRatio,
  };
  const maximum = Math.max(
    statistics.maximum,
    HIGH_REPROJECTION_ERROR_PX,
    ...errors.flatMap((item) => [
      item.rotating,
      item.refinedOverall,
    ]).filter(Number.isFinite),
  );
  const topPoints = reprojectionChartPoints(errors, "top", { maximum });
  const sidePoints = reprojectionChartPoints(errors, "side", { maximum });
  const overallPoints = reprojectionChartPoints(errors, "overall", { maximum });
  const rotatingPoints = reprojectionChartPoints(errors, "rotating", { maximum });
  const refinedPoints = reprojectionChartPoints(
    errors,
    "refinedOverall",
    {
      maximum,
    },
  );
  const thresholdY = CHART_HEIGHT - CHART_PADDING - (
    HIGH_REPROJECTION_ERROR_PX / maximum
  ) * (CHART_HEIGHT - CHART_PADDING * 2);
  const histogram = reprojectionHistogram(errors);
  const histogramMaximum = Math.max(1, ...histogram.map((bin) => bin.count));
  const highFrames = errors.filter((item) => (
    isHighReprojectionError(item)
  ));

  return (
    <div className="grid gap-4">
      <div className="grid gap-3 min-[520px]:grid-cols-2 min-[900px]:grid-cols-4">
        <StatusCard
          title="俯視平均誤差"
          content={`${statistics.topMean.toFixed(2)} px`}
          note="平均值"
        />
        <StatusCard
          title="側視平均誤差"
          content={`${statistics.sideMean.toFixed(2)} px`}
          note="平均值"
        />
        <StatusCard
          title="整體平均誤差"
          content={`${statistics.overallMean.toFixed(2)} px`}
          note={`標準差 ${statistics.standardDeviation.toFixed(2)} px`}
        />
        <StatusCard
          title="高誤差影格"
          content={statistics.highCount}
          note={`> ${HIGH_REPROJECTION_ERROR_PX} px · ${(statistics.highRatio * 100).toFixed(1)}%`}
        />
      </div>

      <div className="grid gap-4 min-[980px]:grid-cols-[minmax(0,1.4fr)_minmax(18rem,0.6fr)]">
        <InnerPanel>
          <SubsectionHeader
            title="每影格重投影誤差"
            description="同圖顯示俯視、側視、環繞、頂+側基準與多視角精修誤差；紅色虛線為 10 px 參考線。"
          />
          <div className="aspect-[19/9] min-w-0 overflow-hidden rounded-xl border border-white/15 bg-black/20">
            <svg
              className="size-full"
              viewBox={`0 0 ${CHART_WIDTH} ${CHART_HEIGHT}`}
              role="img"
              aria-label="重投影誤差隨影格變化圖"
            >
              <line
                x1={CHART_PADDING}
                y1={thresholdY}
                x2={CHART_WIDTH - CHART_PADDING}
                y2={thresholdY}
                stroke="#fb7185"
                strokeWidth="2"
                strokeDasharray="8 6"
              />
              <polyline
                points={pointsAttribute(topPoints)}
                fill="none"
                stroke="#34d399"
                strokeWidth="2"
              />
              <polyline
                points={pointsAttribute(sidePoints)}
                fill="none"
                stroke="#fbbf24"
                strokeWidth="2"
              />
              <polyline
                points={pointsAttribute(overallPoints)}
                fill="none"
                stroke="#d4d4d8"
                strokeWidth="2"
              />
              {rotatingPoints.length ? (
                <polyline
                  points={pointsAttribute(rotatingPoints)}
                  fill="none"
                  stroke="#f472b6"
                  strokeWidth="2"
                />
              ) : null}
              {refinedPoints.length ? (
                <polyline
                  points={pointsAttribute(refinedPoints)}
                  fill="none"
                  stroke="#67e8f9"
                  strokeWidth="2.5"
                />
              ) : null}
              {overallPoints.filter((point) => (
                isHighReprojectionError(point)
              )).map((point) => (
                <circle
                  key={`error-${point.frameId}`}
                  cx={point.plotX}
                  cy={point.plotY}
                  r="4"
                  fill="#fb7185"
                >
                  <title>{errorPointTitle(point)}</title>
                </circle>
              ))}
              <text
                x={CHART_PADDING}
                y="20"
                fill="#a3a3a3"
                fontSize="12"
                fontWeight="700"
              >
                最大 {maximum.toFixed(2)} px
              </text>
            </svg>
          </div>
          <div className="flex flex-wrap gap-3 text-xs font-semibold text-neutral-400">
            <span><i className="mr-1 inline-block size-2 rounded-full bg-emerald-400" />俯視</span>
            <span><i className="mr-1 inline-block size-2 rounded-full bg-amber-400" />側視</span>
            <span><i className="mr-1 inline-block size-2 rounded-full bg-neutral-300" />整體</span>
            {rotatingPoints.length ? (
              <span><i className="mr-1 inline-block size-2 rounded-full bg-pink-400" />環繞</span>
            ) : null}
            {refinedPoints.length ? (
              <span><i className="mr-1 inline-block size-2 rounded-full bg-cyan-300" />精修整體</span>
            ) : null}
            <span><i className="mr-1 inline-block size-2 rounded-full bg-rose-400" />高誤差</span>
          </div>
        </InnerPanel>

        <InnerPanel>
          <SubsectionHeader
            title="誤差分布"
            description={`最大誤差 ${statistics.maximum.toFixed(2)} px。`}
          />
          <div className="grid h-56 grid-cols-8 items-end gap-1 rounded-xl border border-white/15 bg-black/20 p-3">
            {histogram.map((
              bin,
              index,
            ) => (
              <div
                key={`${bin.start}-${bin.end}`}
                className="grid h-full min-w-0 content-end gap-1"
              >
                <span className="text-center text-[10px] font-bold text-neutral-500">
                  {bin.count}
                </span>
                <div
                  className="min-h-0.5 rounded-t bg-emerald-300"
                  style={{
                    height: `${Math.max(2, bin.count / histogramMaximum * 100)}%`,
                  }}
                  title={`${bin.start.toFixed(1)}–${bin.end.toFixed(1)} px：${bin.count} 個`}
                />
                <span className="truncate text-center text-[9px] font-semibold text-neutral-600">
                  {index === 0 ? "0" : bin.start.toFixed(1)}
                </span>
              </div>
            ))}
          </div>
          <div>
            <h4 className="m-0 text-sm font-black text-neutral-200">高誤差影格</h4>
            <p className="mt-2 mb-0 max-h-24 overflow-y-auto text-xs font-semibold leading-5 text-neutral-400">
              {highFrames.length
                ? highFrames.map((item) => item.frameId).join("、")
                : `沒有任一視角誤差大於 ${HIGH_REPROJECTION_ERROR_PX} px 的影格。`
              }
            </p>
          </div>
        </InnerPanel>
      </div>
    </div>
  );
}

import { FiCheck } from "react-icons/fi";

import Tooltip from "@/components/Tooltip";

import { intrinsicCoverageSummary } from "../lib/calibrationUtils";

export default function CalibrationCoverageMap({ run }) {
  const summary = intrinsicCoverageSummary(run);
  const metrics = [
    {
      label: "有效樣本",
      value: `${summary.sampleCount} 張`,
      requirement: `至少 ${summary.requiredSampleCount} 張`,
      complete: summary.sampleCount >= summary.requiredSampleCount,
    },
    {
      label: "覆蓋率",
      value: `${summary.coverageRate}%`,
      complete: summary.occupiedCellCount >= summary.requiredGridCellCount,
    },
    {
      label: "覆蓋位置",
      value: `${summary.occupiedCellCount} 區`,
      requirement: `至少 ${summary.requiredGridCellCount} 區`,
      complete: summary.occupiedCellCount >= summary.requiredGridCellCount,
    },
    {
      label: "邊緣樣本",
      value: `${summary.edgeSampleCount} 張`,
      requirement: `至少 ${summary.requiredEdgeSampleCount} 張`,
      complete: summary.edgeSampleCount >= summary.requiredEdgeSampleCount,
    },
    {
      label: "遠近變化",
      value: summary.scaleReady ? "足夠" : "不足",
      complete: summary.scaleReady,
    },
    {
      label: "姿態變化",
      value: summary.poseReady ? "足夠" : "不足",
      complete: summary.poseReady,
    },
  ];
  const coverageLabel = summary.ready
    ? "校正覆蓋條件已完成"
    : `目前覆蓋 ${summary.occupiedCellCount} 個區域，尚未完成校正覆蓋條件`;
  const guidance = summary.guidance.length > 0
    ? summary.guidance.join("；")
    : "再補拍一張不同位置與角度的校正板";

  return (
    <figure className="m-0 grid gap-3 rounded-xl border border-white/10 bg-black/10 p-3">
      <div className="flex min-w-0 items-center justify-between gap-3">
        <figcaption className="text-xs font-black text-neutral-200">
          校正覆蓋圖
        </figcaption>
        <span className="text-[11px] font-bold text-neutral-400">
          {summary.occupiedCellCount}/9 區
        </span>
      </div>

      <div
        className="relative aspect-video overflow-hidden rounded-xl border border-white/15 bg-[#08110d]"
        role="img"
        aria-label={coverageLabel}
      >
        <div
          className="absolute inset-0 grid grid-cols-3 grid-rows-3"
          aria-hidden="true"
        >
          {summary.cells.map((cell) => (
            <div
              className={`grid min-w-0 place-items-center border-white/10 ${cell.column < 2 ? "border-r" : ""
                } ${cell.row < 2 ? "border-b" : ""
                } ${cell.covered
                  ? "bg-emerald-400/15 text-emerald-200"
                  : "bg-black/10 text-neutral-600"
                }`}
              key={`${cell.column}:${cell.row}`}
            >
              <span className="flex items-center gap-1 text-[10px] font-black">
                {cell.covered ? (
                  <FiCheck
                    className="size-3.5 shrink-0"
                    aria-hidden="true"
                  />
                ) : null}
                {cell.label}
              </span>
            </div>
          ))}
        </div>

        {summary.points.map((point) => (
          <span
            className="absolute z-10 size-2 -translate-x-1/2 -translate-y-1/2 rounded-full border border-[#08110d] bg-white shadow-sm"
            style={{
              left: `${point.x * 100}%`,
              top: `${point.y * 100}%`,
            }}
            aria-hidden="true"
            key={point.id}
          />
        ))}
      </div>

      <dl className="relative grid grid-flow-col grid-rows-2 px-2 gap-x-2 gap-y-2 border-t border-white/10 pt-3 auto-cols-fr before:pointer-events-none before:absolute before:top-3 before:bottom-0 before:left-[33.333%] before:w-px before:bg-white/10 before:content-[''] after:pointer-events-none after:absolute after:top-3 after:bottom-0 after:left-[66.666%] after:w-px after:bg-white/10 after:content-['']">
        {metrics.map((metric, index) => (
          <div
            className={`flex min-h-6 min-w-0 items-center justify-between gap-2 ${index < 2
              ? "pr-3"
              : index < 4
                ? "px-3"
                : "pl-3"
              }`}
            key={metric.label}
          >
            <dt
              className={`relative min-w-0 whitespace-nowrap ${
                metric.requirement ? "group cursor-help" : ""
              }`}
            >
              <span className="text-xs font-bold text-neutral-200">
                {metric.label}
              </span>
              {metric.requirement ? (
                <Tooltip>
                  {metric.requirement}
                </Tooltip>
              ) : null}
            </dt>
            <dd className="m-0 flex shrink-0 items-baseline gap-1">
              <span
                className={`text-xs font-black ${metric.complete ? "text-emerald-200" : "text-amber-200"
                  }`}
              >
                {metric.value}
              </span>
            </dd>
          </div>
        ))}
      </dl>

      <div className="grid grid-cols-[auto_minmax(0,1fr)] items-start gap-2 border-t border-white/10 pt-3 text-xs leading-5">
        <span
          className={`inline-flex min-h-6 items-center rounded-full border px-2 text-[10px] font-black ${summary.ready
            ? "border-emerald-200/70 bg-emerald-500/15 text-emerald-200"
            : "border-amber-200/70 bg-amber-500/15 text-amber-200"
            }`}
        >
          {summary.ready ? "完成" : "建議"}
        </span>
        <p className="m-0 pt-0.5 font-bold text-neutral-300">
          {summary.ready
            ? "覆蓋條件已完成，可以開始計算。"
            : `${guidance}。`
          }
        </p>
      </div>
    </figure>
  );
}

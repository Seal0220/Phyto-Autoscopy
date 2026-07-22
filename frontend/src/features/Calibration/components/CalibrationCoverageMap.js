import { FiCheck } from "react-icons/fi";

import InformationGrid from "@/components/data/InformationGrid";

import { intrinsicCoverageSummary } from "../lib/calibrationUtils";

export default function CalibrationCoverageMap({ run }) {
  const summary = intrinsicCoverageSummary(run);
  const metrics = [
    {
      label: "有效樣本",
      value: `${summary.sampleCount} 張`,
      requirement: `至少 ${summary.requiredSampleCount} 張`,
      tone: summary.sampleCount >= summary.requiredSampleCount
        ? "success"
        : "warning",
    },
    {
      label: "覆蓋率",
      value: `${summary.coverageRate}%`,
      tone: summary.occupiedCellCount >= summary.requiredGridCellCount
        ? "success"
        : "warning",
    },
    {
      label: "覆蓋位置",
      value: `${summary.occupiedCellCount} 區`,
      requirement: `至少 ${summary.requiredGridCellCount} 區`,
      tone: summary.occupiedCellCount >= summary.requiredGridCellCount
        ? "success"
        : "warning",
    },
    {
      label: "邊緣樣本",
      value: `${summary.edgeSampleCount} 張`,
      requirement: `至少 ${summary.requiredEdgeSampleCount} 張`,
      tone: summary.edgeSampleCount >= summary.requiredEdgeSampleCount
        ? "success"
        : "warning",
    },
    {
      label: "遠近變化",
      value: summary.scaleReady ? "足夠" : "不足",
      tone: summary.scaleReady ? "success" : "warning",
    },
    {
      label: "姿態變化",
      value: summary.poseReady ? "足夠" : "不足",
      tone: summary.poseReady ? "success" : "warning",
    },
  ];
  const coverageLabel = summary.ready
    ? "校正覆蓋條件已完成"
    : `目前覆蓋 ${summary.occupiedCellCount} 個區域，尚未完成校正覆蓋條件`;
  const guidance = summary.guidance.length > 0
    ? summary.guidance.join("；")
    : "再補拍一張不同位置與角度的校正板";

  return (
    <figure className="m-0 grid gap-3 rounded-xl border border-white/15 bg-black/15 p-3">
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
              className={`grid min-w-0 place-items-center border-white/15 ${cell.column < 2 ? "border-r" : ""
                } ${cell.row < 2 ? "border-b" : ""
                } ${cell.covered
                  ? "bg-emerald-400/15 text-emerald-200"
                  : "bg-black/15 text-neutral-600"
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

      <InformationGrid
        items={metrics}
        rows={2}
      />

      <div className="grid grid-cols-[auto_minmax(0,1fr)] items-start gap-2 border-t border-white/15 pt-3 text-xs leading-5">
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

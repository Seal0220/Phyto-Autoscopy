import InnerPanel from "@/components/panels/InnerPanel";
import SubsectionHeader from "@/components/headers/SubsectionHeader";
import { analysisRoundResultsUrl } from "@/features/AnalysisRun/lib/analysisTipResultsUtils";

import { formalTrajectoryModeColors } from "../lib/trajectoryUtils";
import {
  imageTipPlotLayout,
  imageTipTrajectorySeries,
} from "../lib/imageTipTrajectoryUtils";

const CAMERAS = [
  { id: "top", label: "俯視尖端軌跡" },
  { id: "side", label: "側視尖端軌跡" },
];
const TICKS = [0, .25, .5, .75, 1];

export default function TrajectoryViewerImageTipCharts({
  analysisId,
  rounds,
  resolved,
}) {
  const colors = formalTrajectoryModeColors(rounds);
  return (
    <InnerPanel>
      <SubsectionHeader
        title="影像尖端軌跡"
        description="變形校正影像的像素座標（px）；各鏡頭各自成圖，缺失處中斷。點選軌跡點可查看或修改該輪尖端。"
      />
      <div className="grid min-w-0 gap-3 min-[900px]:grid-cols-2">
        {CAMERAS.map((camera) => {
          const series = imageTipTrajectorySeries(rounds, resolved, camera.id);
          const layout = imageTipPlotLayout(series);
          return (
            <section
              key={camera.id}
              className="grid min-w-0 content-start gap-2 rounded-xl border border-white/15 bg-black/15 p-3"
              aria-label={camera.label}
            >
              <h4 className="m-0 text-sm font-black text-white">
                {camera.label} · {series.reduce((count, item) => count + item.points.length, 0)} 點
              </h4>
              {layout ? (
                <svg
                  viewBox="0 0 640 300"
                  className="w-full"
                  role="group"
                  aria-label={`${camera.label}；X 向右、Y 向下，單位像素`}
                >
                  {TICKS.map((ratio) => (
                    <g key={ratio}>
                      <line
                        x1={48 + ratio * 560}
                        x2={48 + ratio * 560}
                        y1={16}
                        y2={256}
                        stroke="rgba(255,255,255,.1)"
                      />
                      <line
                        x1={48}
                        x2={608}
                        y1={16 + ratio * 240}
                        y2={16 + ratio * 240}
                        stroke="rgba(255,255,255,.1)"
                      />
                      <text
                        x={48 + ratio * 560}
                        y={276}
                        textAnchor="middle"
                        className="fill-neutral-400 text-[10px]"
                      >
                        {(layout.left + ratio * (layout.right - layout.left)).toFixed(1)}
                      </text>
                      <text
                        x={42}
                        y={20 + ratio * 240}
                        textAnchor="end"
                        className="fill-neutral-400 text-[10px]"
                      >
                        {(layout.top + ratio * (layout.bottom - layout.top)).toFixed(1)}
                      </text>
                    </g>
                  ))}
                  <text
                    x={330}
                    y={294}
                    textAnchor="middle"
                    className="fill-neutral-400 text-[11px]"
                  >X（px）</text>
                  <text
                    x={48}
                    y={8}
                    className="fill-neutral-400 text-[11px]"
                  >Y（px）</text>
                  {series.map((segment) => (
                    <g key={`${segment.modeId}:${segment.points[0].roundKey}`}>
                      <polyline
                        fill="none"
                        stroke={colors[segment.modeId]}
                        strokeWidth={1.5}
                        points={segment.points.map((point) => (
                          `${layout.projectX(point.x_px)},${layout.projectY(point.y_px)}`
                        )).join(" ")}
                      />
                      {segment.points.map((point) => (
                        <a
                          key={point.roundKey}
                          href={analysisRoundResultsUrl(analysisId, point.roundKey)}
                          aria-label={`查看 ${segment.modeId} ${point.roundId} 尖端`}
                          className="group"
                        >
                          <circle
                            cx={layout.projectX(point.x_px)}
                            cy={layout.projectY(point.y_px)}
                            r={4}
                            fill={point.manuallyCorrected ? "white" : colors[segment.modeId]}
                            className="stroke-transparent stroke-2 transition-colors group-hover:stroke-white group-focus-visible:stroke-white"
                          />
                          <title>{`${segment.modeId} · ${point.roundId}：${point.x_px.toFixed(2)}, ${point.y_px.toFixed(2)} px`}</title>
                        </a>
                      ))}
                    </g>
                  ))}
                </svg>
              ) : (
                <p className="m-0 py-8 text-center text-sm font-semibold text-neutral-400">
                  此鏡頭尚無已確認的影像尖端位置。
                </p>
              )}
            </section>
          );
        })}
      </div>
    </InnerPanel>
  );
}

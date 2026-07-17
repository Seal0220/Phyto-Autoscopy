import InnerPanel from "@/components/panels/InnerPanel";
import SubsectionHeader from "@/components/headers/SubsectionHeader";

import {
  DETECTION_CATEGORIES,
  DETECTION_META,
} from "../lib/trajectoryUtils";

function percentage(value) {
  return `${(Number(value || 0) * 100).toFixed(1)}%`;
}

export default function TrajectoryViewerDetectionSummary({
  summary,
}) {
  return (
    <InnerPanel>
      <SubsectionHeader
        title="偵測類型統計"
        description="統計包含俯視、側視與兩者合計；缺失與無效亦完整列出。"
      />
      <div className="max-h-[28rem] overflow-auto rounded-xl border border-white/10">
        <table className="w-full min-w-[46rem] border-collapse text-left text-sm">
          <thead className="sticky top-0 z-10 bg-[#13201a] text-xs font-black text-neutral-300">
            <tr>
              <th className="p-3">類型</th>
              <th className="p-3 text-right">俯視數量</th>
              <th className="p-3 text-right">俯視比例</th>
              <th className="p-3 text-right">側視數量</th>
              <th className="p-3 text-right">側視比例</th>
              <th className="p-3 text-right">整體數量</th>
              <th className="p-3 text-right">整體比例</th>
            </tr>
          </thead>
          <tbody>
            {DETECTION_CATEGORIES.map((category) => (
              <tr
                key={category}
                className="border-t border-white/10 bg-black/10"
              >
                <th className="p-3 font-black text-neutral-100">
                  <span
                    className="mr-2 inline-block size-2 rounded-full"
                    style={{ backgroundColor: DETECTION_META[category].color }}
                    aria-hidden="true"
                  />
                  {DETECTION_META[category].label}
                </th>
                <td className="p-3 text-right font-semibold text-neutral-200">
                  {summary.top[category].count}
                </td>
                <td className="p-3 text-right font-semibold text-neutral-400">
                  {percentage(summary.top[category].ratio)}
                </td>
                <td className="p-3 text-right font-semibold text-neutral-200">
                  {summary.side[category].count}
                </td>
                <td className="p-3 text-right font-semibold text-neutral-400">
                  {percentage(summary.side[category].ratio)}
                </td>
                <td className="p-3 text-right font-semibold text-neutral-200">
                  {summary.overall[category].count}
                </td>
                <td className="p-3 text-right font-semibold text-neutral-400">
                  {percentage(summary.overall[category].ratio)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </InnerPanel>
  );
}

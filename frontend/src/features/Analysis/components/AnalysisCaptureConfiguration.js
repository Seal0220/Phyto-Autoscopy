import InformationGrid from "@/components/data/InformationGrid";
import SubsectionHeader from "@/components/headers/SubsectionHeader";
import {
  formatBooleanState,
  formatNumberWithUnit,
  formatOptionalElapsed,
  formatRangeWithUnit,
} from "@/lib/formatUtils";

import { analysisRecordSummaryItems } from "../lib/analysisUtils";

export default function AnalysisCaptureConfiguration({
  configuration = {},
  record,
}) {
  const hasConfiguration = Object.keys(configuration).length > 0;
  const rotationEnabled = configuration.rotation_enabled === true;
  const configurationItems = hasConfiguration
    ? [
      {
        label: "捕捉方式",
        value: configuration.rotation_enabled === true
          ? "旋臂往復捕捉"
          : configuration.rotation_enabled === false
            ? "固定三鏡頭捕捉"
            : "尚無資料",
      },
      ...(rotationEnabled
        ? [
          {
            label: "總輪數",
            value: formatNumberWithUnit(configuration.total_cycles, "輪"),
          },
          {
            label: "每輪間隔",
            value: formatOptionalElapsed(configuration.cycle_interval_seconds),
          },
          {
            label: "角度範圍",
            value: formatRangeWithUnit(
              configuration.rotation_start_deg,
              configuration.rotation_end_deg,
              "度",
            ),
          },
          {
            label: "角度誤差",
            value: formatNumberWithUnit(configuration.angle_tolerance_deg, "度"),
          },
          {
            label: "穩定等待",
            value: formatNumberWithUnit(configuration.stabilization_delay_ms, "毫秒"),
          },
          {
            label: "往返皆擷取",
            value: formatBooleanState(configuration.capture_on_return),
          },
          {
            label: "結束回原點",
            value: formatBooleanState(configuration.return_to_origin),
          },
          {
            label: "旋臂高度",
            value: formatNumberWithUnit(configuration.arm_height_mm, "mm"),
          },
        ]
        : [
          {
            label: "總時長",
            value: formatOptionalElapsed(configuration.duration_seconds),
          },
        ]),
    ]
    : [
      {
        label: "捕捉配置",
        value: "尚無資料",
        tone: "neutral",
      },
    ];
  return (
    <div className="grid min-w-0 gap-3">
      <SubsectionHeader
        title="紀錄摘要"
        titleMode={1}
      />
      <InformationGrid
        items={analysisRecordSummaryItems(record).map((item) => ({
          ...item,
          truncate: true,
        }))}
        rows={2}
        stackAtSmall
      />
      <SubsectionHeader
        title="原始擷取設定"
        description="來自此紀錄，分析時不會修改。"
        titleMode={1}
      />
      <InformationGrid
        items={configurationItems.map((item) => ({
          ...item,
          truncate: true,
        }))}
        rows={2}
        minimumColumnWidth
        scroll
      />
    </div>
  );
}

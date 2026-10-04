import InformationGrid from "@/components/data/InformationGrid";
import SubsectionHeader from "@/components/headers/SubsectionHeader";
import InnerPanel from "@/components/panels/InnerPanel";

import AnalysisRunImage from "./AnalysisRunImage";

export default function AnalysisRunProcessingImages({
  analysisId,
  preview,
  status,
}) {
  const views = preview?.views || [];
  const diagnostics = preview?.diagnostics || {};

  return (
    <InnerPanel>
      <SubsectionHeader
        title={status === "failed" ? "失敗時的處理影像" : "目前處理影像"}
        description={preview?.message}
      />
      {views.length ? (
        <>
          <p className="m-0 break-all text-xs font-semibold text-neutral-400">
            {preview.round_key}
          </p>
          <div className="grid min-w-0 gap-3 min-[720px]:grid-cols-2 min-[1180px]:grid-cols-3">
            {views.map((view) => (
              <AnalysisRunImage
                key={`${view.view_id}:${preview.coordinate_space}`}
                analysisId={analysisId}
                view={view}
                coordinateSpace={preview.coordinate_space}
              />
            ))}
          </div>
        </>
      ) : (
        <p className="m-0 text-sm font-semibold text-neutral-400">
          尚無處理影像；可展開各輪結果查看來源影像。
        </p>
      )}
      {diagnostics.matched_features !== undefined ? (
        <InformationGrid
          items={[
            { label: "俯視特徵", value: diagnostics.top_features ?? "—" },
            { label: "側視特徵", value: diagnostics.side_features ?? "—" },
            { label: "共同配對", value: diagnostics.matched_features },
            { label: "幾何內點", value: diagnostics.geometric_inliers ?? "—" },
            { label: "所需內點", value: diagnostics.required_inliers ?? "—" },
            { label: "檢查結果", value: diagnostics.rejection_reason || "幾何檢查通過" },
          ]}
          rows={2}
          stackAtSmall
        />
      ) : null}
      {preview?.artifact_path ? (
        <AnalysisRunImage
          key={preview.artifact_path}
          analysisId={analysisId}
          artifactPath={preview.artifact_path}
          revision={preview.updated_at}
          label="雙鏡頭特徵配對圖"
        />
      ) : null}
    </InnerPanel>
  );
}

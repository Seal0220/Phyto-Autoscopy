import InformationGrid from "@/components/data/InformationGrid";
import SubsectionHeader from "@/components/headers/SubsectionHeader";
import {
  NumericInput,
  SelectInput,
} from "@/components/inputs/Input";
import { ToggleRow } from "@/components/inputs/Toggle";
import InnerPanel from "@/components/panels/InnerPanel";
import { StatusPill } from "@/components/panels/Panel";

import {
  ANALYSIS_METHODS,
  RECONSTRUCTION_QUALITY_OPTIONS,
} from "../analysisConfig";

const BACKGROUND_TOGGLES = [
  ["generatePlantMask", "建立植物遮罩", "由單張影像與空間範圍自動推導，不需人工指定區域。"],
  ["usePlantMaskInLoss", "在模型訓練中使用植物遮罩", "降低背景對純植物模型的影響。"],
  ["preserveSceneModel", "保留完整場景模型", "完整模型與純植物模型分開保存，互不覆蓋。"],
  ["exportPlantModel", "建立純植物模型", "模型建立完成後再依世界範圍、群聚與遮罩移除背景。"],
  ["saveBackgroundModel", "保存背景模型", "額外保存從植物模型排除的背景結果。"],
];

const TIP_TOGGLES = [
  ["useSkeletonRefinement", "使用植物骨架精修", "以主生長軸與骨架端點約束三維尖端標記。"],
  ["useTemporalPrior", "使用上一輪弱時序先驗", "只協助排除不合理跳點，不強迫尖端停留在舊位置。"],
  ["waitForLowConfidenceReview", "低信心時等待人工確認", "保留自動結果並進入尖端標記人工確認流程。"],
  ["exportAll2dCandidates", "輸出全部二維候選", "保存各去畸變影像中的候選與排除原因。"],
  ["saveReprojectionOverlays", "保存重投影疊圖", "保存尖端標記投影回各相機影像的診斷結果。"],
];

const OUTPUT_TOGGLES = [
  ["saveGaussianModel", "Gaussian 模型"],
  ["exportScenePointCloud", "完整點雲"],
  ["exportPlantPointCloud", "純植物點雲"],
  ["exportSkeleton", "植物骨架"],
  ["exportTipMarkers", "每輪尖端標記"],
  ["exportTrajectoryCsv", "尖端標記軌跡 CSV"],
  ["saveModelPreviews", "模型預覽"],
  ["saveDiagnostics", "診斷資料"],
  ["saveCheckpoints", "模型 Checkpoint"],
];

const FIXED_TIP_TOGGLE_KEYS = new Set([
  "useTemporalPrior",
  "waitForLowConfidenceReview",
  "exportAll2dCandidates",
  "saveReprojectionOverlays",
]);

const FIXED_OUTPUT_KEYS = new Set([
  "exportTipMarkers",
  "exportTrajectoryCsv",
  "saveDiagnostics",
]);

const REQUIRED_BACKGROUND_KEYS = new Set([
  "generatePlantMask",
]);

function ToggleCollection({
  items,
  parameters,
  onChange,
  disabledKeys,
}) {
  return (
    <div className="grid gap-3 min-[720px]:grid-cols-2">
      {items.map(([key, label, description]) => (
        <ToggleRow
          checked={Boolean(parameters[key])}
          description={description}
          disabled={disabledKeys?.has(key)}
          key={key}
          label={label}
          onClick={disabledKeys?.has(key)
            ? undefined
            : () => onChange(
              key,
              !parameters[key],
            )
          }
        />
      ))}
    </div>
  );
}

export default function AnalysisSetupReconstructionStep({
  method,
  parameters,
  manualReviewRequired,
  onChange,
  onManualReviewChange,
}) {
  const selectedMethod = ANALYSIS_METHODS[method];
  const buildsRoundModels = method === "rotating";
  const visibleTipToggles = buildsRoundModels
    ? TIP_TOGGLES
    : TIP_TOGGLES.filter(([key]) => FIXED_TIP_TOGGLE_KEYS.has(key));
  const visibleOutputToggles = buildsRoundModels
    ? OUTPUT_TOGGLES
    : OUTPUT_TOGGLES.filter(([key]) => FIXED_OUTPUT_KEYS.has(key));

  return (
    <section
      className="grid gap-4"
      aria-labelledby="analysis-reconstruction-step-title"
    >
      <SubsectionHeader
        titleId="analysis-reconstruction-step-title"
        title="重建與尖端分析"
        description={selectedMethod.description}
      >
        <StatusPill tone="success">
          {selectedMethod.label}
        </StatusPill>
      </SubsectionHeader>

      {buildsRoundModels ? (
        <InnerPanel>
          <SubsectionHeader
            title="三維模型"
            description="一般設定只選擇品質；底層訓練參數由品質模式管理。"
            titleMode={1}
          />
          <div className="grid gap-3 min-[720px]:grid-cols-2">
            <SelectInput
              id="analysis-reconstruction-quality"
              label="模型品質"
              value={parameters.qualityPreset}
              onValueChange={(value) => onChange(
                "qualityPreset",
                value,
              )}
              options={RECONSTRUCTION_QUALITY_OPTIONS}
            />
            <InformationGrid
              items={[
                {
                  label: "模型後端",
                  value: parameters.reconstructionBackend === "gsplat_3dgs"
                    ? "gsplat"
                    : "Graphdeco",
                },
                {
                  label: "世界座標",
                  value: "ArUco／mm",
                },
              ]}
              border="none"
              rows={2}
            />
          </div>
        </InnerPanel>
      ) : null}

      <InnerPanel>
        <SubsectionHeader
          title="相機姿態"
          description="ArUco 世界姿態固定啟用；多視角精修失敗時保留原始姿態與警告。"
          titleMode={1}
        />
        <div
          className={`grid gap-3 ${
            buildsRoundModels ? "min-[720px]:grid-cols-2" : ""
          }`}
        >
          <ToggleRow
            checked
            disabled
            label="使用 ArUco 世界姿態"
            description="每張去畸變影像都必須先註冊到公制世界座標。"
          />
          {buildsRoundModels ? (
            <ToggleRow
              checked={parameters.useBundleAdjustment}
              label="多視角姿態精修"
              description="使用特徵對應與受 ArUco 約束的 Bundle Adjustment 精修姿態。"
              onClick={() => onChange(
                "useBundleAdjustment",
                !parameters.useBundleAdjustment,
              )}
            />
          ) : null}
        </div>
      </InnerPanel>

      <InnerPanel>
        <SubsectionHeader
          title={buildsRoundModels ? "背景處理" : "影像處理"}
          description={buildsRoundModels
            ? "模型建立前保留必要背景特徵，完成後再建立獨立的純植物輸出。"
            : "由各去畸變影像建立植物遮罩，協助固定雙鏡頭的尖端候選分析。"
          }
          titleMode={1}
        />
        <ToggleCollection
          items={buildsRoundModels
            ? BACKGROUND_TOGGLES
            : [BACKGROUND_TOGGLES[0]]
          }
          parameters={parameters}
          onChange={onChange}
          disabledKeys={REQUIRED_BACKGROUND_KEYS}
        />
      </InnerPanel>

      <InnerPanel>
        <SubsectionHeader
          title="尖端標記"
          description="尖端標記由多視角候選、模型表面、植物骨架與弱時序先驗共同決定。"
          titleMode={1}
        />
        <div className="grid gap-3 min-[720px]:grid-cols-3">
          <NumericInput
            id="analysis-minimum-tip-confidence"
            label="最低尖端標記信心"
            value={parameters.minimumTipConfidence}
            onValueChange={(value) => onChange(
              "minimumTipConfidence",
              value,
            )}
            min={0}
            max={1}
            step={0.05}
            required
          />
          <NumericInput
            id="analysis-minimum-supporting-views"
            label="最低支持視角數"
            value={parameters.minimumSupportingViews}
            onValueChange={(value) => onChange(
              "minimumSupportingViews",
              value,
            )}
            min={2}
            step={1}
            suffix="個"
            required
          />
          <NumericInput
            id="analysis-tip-reprojection-error"
            label="最大重投影誤差"
            value={parameters.maximumTipReprojectionError}
            onValueChange={(value) => onChange(
              "maximumTipReprojectionError",
              value,
            )}
            min={0.1}
            step={0.1}
            suffix="px"
            required
          />
        </div>
        <ToggleCollection
          items={visibleTipToggles}
          parameters={parameters}
          onChange={onChange}
        />
        <ToggleRow
          checked={manualReviewRequired}
          label="執行人工確認"
          description="低信心尖端標記與失敗輪次保留原始結果，等待操作人員確認。"
          onClick={() => onManualReviewChange(!manualReviewRequired)}
        />
      </InnerPanel>

      <InnerPanel>
        <SubsectionHeader
          title="輸出"
          description="每輪輸出與跨輪軌跡皆寫入獨立分析目錄，不修改原始捕捉紀錄。"
          titleMode={1}
        />
        <div className="grid gap-3 min-[720px]:grid-cols-2 min-[1040px]:grid-cols-3">
          {visibleOutputToggles.map(([key, label]) => (
            <ToggleRow
              checked={Boolean(parameters[key])}
              key={key}
              label={label}
              onClick={() => onChange(
                key,
                !parameters[key],
              )}
            />
          ))}
        </div>
      </InnerPanel>
    </section>
  );
}

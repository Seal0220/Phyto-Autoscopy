import SubsectionHeader from "@/components/headers/SubsectionHeader";
import {
  NumericInput,
  SelectInput,
} from "@/components/inputs/Input";
import { ToggleRow } from "@/components/inputs/Toggle";
import DisclosurePanel from "@/components/panels/DisclosurePanel";
import InnerPanel from "@/components/panels/InnerPanel";
import { StatusPill } from "@/components/panels/Panel";

import {
  ANALYSIS_METHODS,
  RECONSTRUCTION_BACKEND_OPTIONS,
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
            description="選擇 Gaussian 建模後端與訓練品質。"
            titleMode={1}
          />
          <div className="grid gap-3 min-[720px]:grid-cols-2">
            <SelectInput
              id="analysis-reconstruction-backend"
              label="模型後端"
              value={parameters.reconstructionBackend}
              onValueChange={(value) => onChange(
                "reconstructionBackend",
                value,
              )}
              options={RECONSTRUCTION_BACKEND_OPTIONS}
            />
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
          </div>
          <DisclosurePanel
            title="進階訓練設定"
            description="品質模式會先帶入建議值；需要時可自行微調。"
          >
            <div className="grid gap-3 min-[720px]:grid-cols-2">
              <NumericInput
                id="analysis-training-iterations"
                label="模型訓練步數"
                value={parameters.trainingIterations}
                onValueChange={(value) => onChange("trainingIterations", value)}
                min={500}
                max={100000}
                step={500}
                suffix="步"
                required
              />
              {parameters.reconstructionBackend === "gsplat_3dgs" ? (
                <SelectInput
                  id="analysis-image-factor"
                  label="訓練影像縮小倍率"
                  value={parameters.imageFactor}
                  onValueChange={(value) => onChange("imageFactor", value)}
                  options={[
                    { value: "1", label: "原始解析度" },
                    { value: "2", label: "縮小 2 倍" },
                    { value: "4", label: "縮小 4 倍" },
                    { value: "8", label: "縮小 8 倍" },
                  ]}
                />
              ) : null}
            </div>
          </DisclosurePanel>
        </InnerPanel>
      ) : null}

      <InnerPanel>
        <SubsectionHeader
          title="相機姿態"
          description="由校正內參與共同影像特徵估姿；實測基線與俯視高度定尺度，側鏡頭安裝量測可檢查姿態偏差。"
          titleMode={1}
        />
        <div className="grid gap-3 min-[720px]:grid-cols-2">
          <NumericInput
            id="analysis-baseline-mm"
            label="雙鏡頭實測基線"
            description="俯視與側視鏡頭光學中心的直線距離；不可填估計值。"
            value={parameters.baselineMm}
            onValueChange={(value) => onChange("baselineMm", value)}
            min={0.1}
            max={100000}
            step={0.1}
            suffix="mm"
            required
          />
          <NumericInput
            id="analysis-top-height-mm"
            label="俯視鏡頭至平台高度"
            description="俯視鏡頭光學中心到植物所在平台平面的垂直距離；平台定為 Z=0。"
            value={parameters.topHeightMm}
            onValueChange={(value) => onChange("topHeightMm", value)}
            min={0.1}
            max={100000}
            step={0.1}
            suffix="mm"
            required
          />
          <NumericInput
            id="analysis-side-height-mm"
            label="側鏡頭距桌面高度"
            description="選填；側鏡頭光學中心到桌面平面的垂直距離，用於比對估計姿態。"
            value={parameters.sideHeightMm}
            onValueChange={(value) => onChange("sideHeightMm", value)}
            min={0}
            max={10000}
            step={0.1}
            suffix="mm"
          />
          <NumericInput
            id="analysis-side-horizontal-distance-mm"
            label="側鏡頭至中心水平距離"
            description="選填；側鏡頭光學中心到分析原點（俯視鏡頭正下方）的水平距離，用於比對估計姿態。"
            value={parameters.sideHorizontalDistanceMm}
            onValueChange={(value) => onChange("sideHorizontalDistanceMm", value)}
            min={0}
            max={10000}
            step={0.1}
            suffix="mm"
          />
        </div>
        <DisclosurePanel
          title="進階姿態設定"
          description="特徵數、配對與重投影門檻；沒有需要時可保持預設。"
        >
          <div className="grid gap-3 min-[720px]:grid-cols-2 min-[1040px]:grid-cols-3">
          <NumericInput
            id="analysis-feature-count"
            label="每張特徵上限"
            value={parameters.featureCount}
            onValueChange={(value) => onChange("featureCount", value)}
            min={500}
            max={20000}
            step={100}
            suffix="點"
            required
          />
          <NumericInput
            id="analysis-stereo-inliers"
            label="雙鏡頭最少內點"
            value={parameters.minimumStereoInliers}
            onValueChange={(value) => onChange("minimumStereoInliers", value)}
            min={8}
            max={1000}
            step={1}
            suffix="點"
            required
          />
          <NumericInput
            id="analysis-epipolar-error"
            label="極線誤差上限"
            value={parameters.maximumEpipolarErrorPx}
            onValueChange={(value) => onChange("maximumEpipolarErrorPx", value)}
            min={0.1}
            max={20}
            step={0.1}
            suffix="px"
            required
          />
          <NumericInput
            id="analysis-minimum-parallax"
            label="最小視差角"
            description="雙鏡頭共同特徵的中位視差角低於此值時拒絕退化幾何。"
            value={parameters.minimumParallaxDeg}
            onValueChange={(value) => onChange("minimumParallaxDeg", value)}
            min={0.1}
            max={30}
            step={0.1}
            suffix="°"
            required
          />
          <NumericInput
            id="analysis-side-elevation"
            label="側視偏水平上限"
            description="求得的側視鏡頭光軸偏離水平超過此角度時拒絕姿態。"
            value={parameters.maximumSideElevationDeg}
            onValueChange={(value) => onChange("maximumSideElevationDeg", value)}
            min={0}
            max={90}
            step={0.5}
            suffix="°"
            required
          />
          <NumericInput
            id="analysis-stereo-reprojection-error"
            label="雙鏡頭重投影上限"
            value={parameters.maximumStereoReprojectionErrorPx}
            onValueChange={(value) => onChange("maximumStereoReprojectionErrorPx", value)}
            min={0.1}
            max={30}
            step={0.1}
            suffix="px"
            required
          />
          {buildsRoundModels ? (
            <>
              <NumericInput
                id="analysis-rotating-inliers"
                label="旋臂最少內點"
                value={parameters.minimumRotatingInliers}
                onValueChange={(value) => onChange("minimumRotatingInliers", value)}
                min={6}
                max={1000}
                step={1}
                suffix="點"
                required
              />
              <NumericInput
                id="analysis-pnp-reprojection-error"
                label="旋臂重投影上限"
                value={parameters.maximumPnpReprojectionErrorPx}
                onValueChange={(value) => onChange("maximumPnpReprojectionErrorPx", value)}
                min={0.1}
                max={30}
                step={0.1}
                suffix="px"
                required
              />
            </>
          ) : null}
          </div>
          {buildsRoundModels ? (
            <div className="grid gap-3 min-[720px]:grid-cols-2">
            <ToggleRow
              checked={parameters.useMotorInterpolation}
              label="馬達角度補足姿態"
              description="旋臂影格特徵不足時，只在前後兩張有效姿態之間依角度補足。"
              onClick={() => onChange(
                "useMotorInterpolation",
                !parameters.useMotorInterpolation,
              )}
            />
            <ToggleRow
              checked={parameters.useBundleAdjustment}
              label="多視角姿態精修"
              description="固定雙鏡頭基線與內參，僅精修旋臂姿態。"
              onClick={() => onChange(
                "useBundleAdjustment",
                !parameters.useBundleAdjustment,
              )}
            />
            </div>
          ) : null}
        </DisclosurePanel>
      </InnerPanel>

      <DisclosurePanel
        title={buildsRoundModels ? "背景處理" : "影像處理"}
        description={buildsRoundModels
          ? "模型建立前保留必要背景特徵，完成後再建立獨立的純植物輸出。"
          : "由各去畸變影像建立植物遮罩，協助固定雙鏡頭的尖端候選分析。"
        }
      >
        <ToggleCollection
          items={buildsRoundModels
            ? BACKGROUND_TOGGLES
            : [BACKGROUND_TOGGLES[0]]
          }
          parameters={parameters}
          onChange={onChange}
          disabledKeys={REQUIRED_BACKGROUND_KEYS}
        />
      </DisclosurePanel>

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
        <ToggleRow
          checked={manualReviewRequired}
          label="執行人工確認"
          description="低信心尖端標記與失敗輪次保留原始結果，等待操作人員確認。"
          onClick={() => onManualReviewChange(!manualReviewRequired)}
        />
        <DisclosurePanel
          title="尖端分析進階選項"
          description="骨架、時序先驗與診斷資料。"
        >
          <ToggleCollection
            items={visibleTipToggles}
            parameters={parameters}
            onChange={onChange}
          />
        </DisclosurePanel>
      </InnerPanel>

      <DisclosurePanel
        title="輸出"
        description="每輪輸出與跨輪軌跡皆寫入獨立分析目錄，不修改原始捕捉紀錄。"
      >
        <div className="grid gap-3 min-[720px]:grid-cols-2 min-[1040px]:grid-cols-3">
          {visibleOutputToggles.map(([key, label]) => (
            <ToggleRow
              checked={Boolean(parameters[key])}
              disabled={key === "saveModelPreviews"
                && parameters.reconstructionBackend === "graphdeco_3dgs"
              }
              key={key}
              label={key === "saveModelPreviews"
                && parameters.reconstructionBackend === "graphdeco_3dgs"
                ? `${label}（Graphdeco 不支援）`
                : label
              }
              onClick={() => onChange(
                key,
                !parameters[key],
              )}
            />
          ))}
        </div>
      </DisclosurePanel>
    </section>
  );
}

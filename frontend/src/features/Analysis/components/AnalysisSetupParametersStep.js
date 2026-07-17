import InnerPanel from "@/components/panels/InnerPanel";
import { StatusPill } from "@/components/panels/Panel";
import SubsectionHeader from "@/components/headers/SubsectionHeader";
import {
  DurationInput,
  SelectInput,
} from "@/components/inputs/Input";
import { ToggleRow } from "@/components/inputs/Toggle";

import {
  ANALYSIS_METHODS,
  HIGH_REPROJECTION_ERROR_THRESHOLD_PX,
  LIGHTING_PARAMETER_FIELDS,
  MINIMUM_PATH_CONNECTIVITY_OPTIONS,
  MOG2_PARAMETER_FIELDS,
  MORPHOLOGY_PARAMETER_FIELDS,
  SIDE_DETECTION_PARAMETER_FIELDS,
  TOP_DETECTION_PARAMETER_FIELDS,
} from "../analysisConfig";
import AnalysisSetupParameterGroup from "./AnalysisSetupParameterGroup";

export default function AnalysisSetupParametersStep({
  method,
  parameters,
  manualReviewRequired,
  onChange,
  onManualReviewChange,
}) {
  const selectedMethod = ANALYSIS_METHODS[method];

  return (
    <section
      className="grid gap-4"
      aria-labelledby="analysis-parameters-step-title"
    >
      <SubsectionHeader
        titleId="analysis-parameters-step-title"
        title="設定論文方法參數"
        description={selectedMethod.description}
      >
        <StatusPill tone="success">{selectedMethod.label}</StatusPill>
      </SubsectionHeader>

      <InnerPanel>
        <dl className="grid gap-3 text-sm min-[720px]:grid-cols-3">
          <div className="min-w-0">
            <dt className="text-xs font-black text-neutral-500">方法名稱</dt>
            <dd className="mt-1 m-0 break-all font-bold text-neutral-100">
              {selectedMethod.label}
            </dd>
          </div>
          <div>
            <dt className="text-xs font-black text-neutral-500">環繞精修</dt>
            <dd className="mt-1 m-0 font-bold text-neutral-100">
              {method === "top_side_rotating"
                ? "依馬達角度計算動態外參"
                : "不使用"
              }
            </dd>
          </div>
          <div>
            <dt className="text-xs font-black text-neutral-500">參考研究</dt>
            <dd className="mt-1 m-0 font-bold text-neutral-100">
              {selectedMethod.reference}
            </dd>
          </div>
        </dl>
      </InnerPanel>

      <AnalysisSetupParameterGroup
        title="MOG2 背景分割"
        description="設定背景模型歷史、變異門檻、學習率與初始化影格數。"
        fields={MOG2_PARAMETER_FIELDS}
        parameters={parameters}
        onChange={onChange}
      >
        <ToggleRow
          checked={parameters.segmentationDetectShadows}
          label="偵測陰影"
          description="OpenCV MOG2 的陰影偵測；第一版預設關閉。"
          onClick={() => onChange(
            "segmentationDetectShadows",
            !parameters.segmentationDetectShadows,
          )}
        />
      </AnalysisSetupParameterGroup>

      <AnalysisSetupParameterGroup
        title="輪廓與 Morphology"
        description="核心大小必須為正奇數；輪廓面積用於排除背景雜訊。"
        fields={MORPHOLOGY_PARAMETER_FIELDS}
        parameters={parameters}
        onChange={onChange}
      />

      <AnalysisSetupParameterGroup
        title="光照切換"
        description="輪廓面積超過門檻時重設背景模型，等待指定影格數後恢復偵測。"
        fields={LIGHTING_PARAMETER_FIELDS}
        parameters={parameters}
        onChange={onChange}
      />

      <AnalysisSetupParameterGroup
        title="俯視尖端偵測"
        description="依植物基部、候選輪廓數與 ROI 更新邊距選擇俯視尖端。"
        fields={TOP_DETECTION_PARAMETER_FIELDS}
        parameters={parameters}
        onChange={onChange}
      >
        <ToggleRow
          checked={parameters.topUpdateRoi}
          label="更新俯視 ROI"
          description="每個有效影格後，以選定植物輪廓的外接矩形加上設定邊距，更新下一影格的搜尋區域。"
          onClick={() => onChange(
            "topUpdateRoi",
            !parameters.topUpdateRoi,
          )}
        />
      </AnalysisSetupParameterGroup>

      <AnalysisSetupParameterGroup
        title="側視尖端與 Epipolar 約束"
        description="以俯視尖端計算 Epipolar Line，再對鄰近輪廓執行 Minimum Path。"
        fields={SIDE_DETECTION_PARAMETER_FIELDS}
        parameters={parameters}
        onChange={onChange}
      >
        <div className="grid gap-3 min-[520px]:grid-cols-2">
          <SelectInput
            id="analysis-minimum-path-connectivity"
            label="Minimum Path 鄰接方式"
            value={parameters.minimumPathConnectivity}
            onValueChange={(value) => onChange(
              "minimumPathConnectivity",
              value,
            )}
            options={MINIMUM_PATH_CONNECTIVITY_OPTIONS}
            description="選擇骨架圖中每個像素可連接的相鄰方向。"
          />
          <div className="grid min-h-11.5 content-center rounded-xl border border-white/10 bg-black/10 px-3 py-2">
            <span className="text-xs font-black text-neutral-500">Minimum Path 邊權重</span>
            <span className="mt-1 text-sm font-bold text-neutral-200">
              距離轉換反比（固定）
            </span>
          </div>
        </div>
        <ToggleRow
          checked={parameters.sideUpdateRoi}
          label="更新側視 ROI"
          description="每個有效影格後，以選定植物輪廓的外接矩形加上設定邊距，更新下一影格的搜尋區域。"
          onClick={() => onChange(
            "sideUpdateRoi",
            !parameters.sideUpdateRoi,
          )}
        />
      </AnalysisSetupParameterGroup>

      <InnerPanel>
        <SubsectionHeader
          title="插值、人工修正與重投影"
          description="缺失位置只使用線性插值；不跨越斷線、未配對或光照切換區段。"
          titleMode={1}
        />
        <div className="grid gap-3 min-[520px]:grid-cols-2">
          <DurationInput
            id="analysis-maximum-interpolation-gap"
            label="最大插值缺口"
            value={parameters.maximumInterpolationGapSeconds}
            onValueChange={(value) => onChange(
              "maximumInterpolationGapSeconds",
              value,
            )}
            unit="seconds"
            description="超過此時間的缺失區段不進行線性插值。"
            required
          />
          <div className="grid min-h-11.5 content-center rounded-xl border border-white/10 bg-black/10 px-3 py-2">
            <span className="text-xs font-black text-neutral-500">
              高重投影誤差門檻
            </span>
            <span className="mt-1 text-sm font-bold text-neutral-200">
              {HIGH_REPROJECTION_ERROR_THRESHOLD_PX} px（固定）
            </span>
            <span className="mt-1 text-xs font-semibold text-neutral-400">
              高於固定門檻的重投影誤差會被標記供人工檢查。
            </span>
          </div>
        </div>
        <div className="grid gap-3">
          <ToggleRow
            checked={manualReviewRequired}
            label="執行人工修正"
            description="自動偵測與插值完成後暫停分析，待人工確認俯視與側視尖端位置。"
            onClick={() => onManualReviewChange(!manualReviewRequired)}
          />
        </div>
      </InnerPanel>
    </section>
  );
}

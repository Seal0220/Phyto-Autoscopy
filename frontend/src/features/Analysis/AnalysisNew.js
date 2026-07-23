"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import {
  FiArrowLeft,
  FiArrowRight,
  FiCheckCircle,
  FiPlay,
  FiRefreshCw,
  FiSave,
} from "react-icons/fi";
import { PiHouseFill } from "react-icons/pi";

import ActionRow from "@/components/actions/ActionRow";
import Button from "@/components/buttons/Button";
import {
  Panel,
  PanelHeader,
} from "@/components/panels/Panel";
import useNotificationsContext from "@/features/Notifications/hooks/useNotificationsContext";

import { ANALYSIS_SETUP_STEPS } from "./analysisConfig";
import AnalysisAvailableRecords from "./components/AnalysisAvailableRecords";
import AnalysisSetupProgress from "./components/AnalysisSetupProgress";
import AnalysisSetupReconstructionStep from "./components/AnalysisSetupReconstructionStep";
import AnalysisSetupSourcesStep from "./components/AnalysisSetupSourcesStep";
import AnalysisSetupSummaryStep from "./components/AnalysisSetupSummaryStep";
import useAnalysisSetup from "./hooks/useAnalysisSetup";

export default function AnalysisNew({
  initialRecordId = "",
}) {
  const router = useRouter();
  const { showNotification } = useNotificationsContext();
  const {
    sources,
    setup,
    currentStep,
    highestStep,
    loading,
    loadError,
    stepError,
    createdRun,
    mutationPending,
    mutationError,
    mutationRequiresRefresh,
    sourceScanning,
    loadOptions,
    selectRecord,
    updateSetup,
    updateCameraSource,
    updateModeSelection,
    updateParameter,
    goToStep,
    nextStep,
    previousStep,
    createRun,
    validateRun,
    startRun,
  } = useAnalysisSetup({
    initialRecordId,
  });
  const selectedSource = sources.find(
    (source) => source.record_id === setup.recordId,
  );
  const hasOptions = sources.length > 0;
  const mutationLocked = Boolean(mutationPending) || mutationRequiresRefresh;

  useEffect(() => {
    if (loadError) showNotification(loadError, "error");
  }, [
    loadError,
    showNotification,
  ]);

  useEffect(() => {
    if (mutationError) showNotification(mutationError, "error");
  }, [
    mutationError,
    showNotification,
  ]);

  useEffect(() => {
    if (stepError) showNotification(stepError, "warning");
  }, [
    showNotification,
    stepError,
  ]);

  useEffect(() => {
    const errors = Array.isArray(setup.sourcePreview?.errors)
      ? setup.sourcePreview.errors
      : [];
    const warnings = Array.isArray(setup.sourcePreview?.warnings)
      ? setup.sourcePreview.warnings
      : [];

    for (const message of [
      ...errors,
      ...warnings,
    ]) {
      showNotification(message, "warning");
    }
  }, [
    setup.sourcePreview,
    showNotification,
  ]);

  function renderStep() {
    if (currentStep === 1) {
      return (
        <AnalysisAvailableRecords
          selectedRecordId={setup.recordId}
          sources={sources}
          onSelect={selectRecord}
        />
      );
    }
    if (currentStep === 2) {
      return (
        <AnalysisSetupSourcesStep
          record={selectedSource}
          setup={setup}
          scanning={sourceScanning}
          onCameraSourceChange={updateCameraSource}
          onModeSelectionChange={updateModeSelection}
        />
      );
    }
    if (currentStep === 3) {
      return (
        <AnalysisSetupReconstructionStep
          method={setup.method}
          parameters={setup.parameters}
          manualReviewRequired={setup.manualReviewRequired}
          onChange={updateParameter}
          onManualReviewChange={(value) => updateSetup(
            "manualReviewRequired",
            value,
          )}
        />
      );
    }
    return (
      <AnalysisSetupSummaryStep
        setup={setup}
        source={selectedSource}
        createdRun={createdRun}
      />
    );
  }

  function finalActions() {
    if (!createdRun) {
      return (
        <Button
          className="ml-auto"
          variant="primary"
          disabled={mutationLocked}
          onClick={() => void createRun()}
        >
          <FiSave
            className="size-4 shrink-0"
            aria-hidden="true"
          />
          {mutationPending === "create" ? "建立中…" : "建立分析"}
        </Button>
      );
    }

    if (createdRun.status === "ready") {
      return (
        <Button
          className="ml-auto"
          variant="primary"
          disabled={mutationLocked}
          onClick={() => void startRun()}
        >
          <FiPlay
            className="size-4 shrink-0"
            aria-hidden="true"
          />
          {mutationPending === "start" ? "啟動中…" : "開始分析"}
        </Button>
      );
    }

    if ([
      "processing",
      "needs_review",
      "reviewing",
      "reconstructing",
      "completed",
      "partially_completed",
    ].includes(createdRun.status)) {
      return (
        <Button
          className="ml-auto"
          variant="primary"
          onClick={() => router.push("/analysis")}
        >
          <PiHouseFill
            className="size-4 shrink-0"
            aria-hidden="true"
          />
          返回分析首頁
        </Button>
      );
    }

    return (
      <Button
        className="ml-auto"
        variant="primary"
        disabled={mutationLocked}
        onClick={() => void validateRun()}
      >
        <FiCheckCircle
          className="size-4 shrink-0"
          aria-hidden="true"
        />
        {mutationPending === "validate" ? "驗證中…" : "驗證分析"}
      </Button>
    );
  }

  return (
    <div className="mx-auto grid w-full max-w-7xl gap-4 pt-24 max-[980px]:pt-32">
        <Panel aria-label="新增分析">
          <PanelHeader
            title="新增分析"
            action={(
              <div className="flex flex-wrap items-center justify-end gap-2">
                {loadError ? (
                  <Button
                    disabled={loading}
                    onClick={() => void loadOptions()}
                  >
                    <FiRefreshCw
                      className="size-4 shrink-0"
                      aria-hidden="true"
                    />
                    {loading ? "重新讀取中…" : "重新讀取"}
                  </Button>
                ) : null}
                <Button onClick={() => router.push("/analysis")}>
                  <PiHouseFill
                    className="size-4 shrink-0"
                    aria-hidden="true"
                  />
                  返回分析首頁
                </Button>
              </div>
            )}
          />

          <div className="grid gap-5 p-5 max-sm:p-4">
            {loading && !hasOptions ? (
              <div
                className="grid min-h-36 place-items-center rounded-xl border border-white/15 bg-black/15 p-4 text-sm font-semibold text-neutral-400"
                role="status"
              >
                讀取分析選項中…
              </div>
            ) : null}

            {(!loadError || hasOptions) && (!loading || hasOptions) ? (
              <>
                <AnalysisSetupProgress
                  currentStep={currentStep}
                  highestStep={highestStep}
                  locked={Boolean(createdRun)}
                  onStepChange={goToStep}
                />

                {renderStep()}

                <ActionRow className="w-full">
                  {mutationRequiresRefresh ? (
                    <Button
                      className="ml-auto"
                      variant="primary"
                      onClick={() => router.push("/analysis")}
                    >
                      <FiRefreshCw
                        className="size-4 shrink-0"
                        aria-hidden="true"
                      />
                      返回並確認狀態
                    </Button>
                  ) : (
                    <>
                      {currentStep > 1 && !createdRun ? (
                        <Button
                          disabled={Boolean(mutationPending)}
                          onClick={previousStep}
                        >
                          <FiArrowLeft
                            className="size-4 shrink-0"
                            aria-hidden="true"
                          />
                          上一步
                        </Button>
                      ) : null}

                      {currentStep < ANALYSIS_SETUP_STEPS.length ? (
                        <Button
                          className="ml-auto"
                          variant="primary"
                          onClick={nextStep}
                        >
                          <FiArrowRight
                            className="size-4 shrink-0"
                            aria-hidden="true"
                          />
                          下一步
                        </Button>
                      ) : finalActions()}
                    </>
                  )}
                </ActionRow>
              </>
            ) : null}
          </div>
        </Panel>
    </div>
  );
}

"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import {
  FiArrowLeft,
  FiArrowRight,
  FiPlay,
} from "react-icons/fi";

import ActionRow from "@/components/actions/ActionRow";
import Button from "@/components/buttons/Button";
import RetryMessage from "@/components/feedback/RetryMessage";
import {
  Panel,
  PanelHeader,
} from "@/components/panels/Panel";
import useNotificationsContext from "@/features/Notifications/hooks/useNotificationsContext";
import useAnalysisSecondaryNavigation from "@/features/MainNavigation/hooks/useAnalysisSecondaryNavigation";

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
    sourceScanProgress,
    sourceScanError,
    retrySourceScan,
    cancelSourceScan,
    loadOptions,
    selectRecord,
    updateSetup,
    updateCameraSource,
    updateModeSelection,
    updateParameter,
    goToStep,
    nextStep,
    previousStep,
    startRun,
  } = useAnalysisSetup({
    initialRecordId,
  });
  const selectedSource = sources.find(
    (source) => source.record_id === setup.recordId,
  );
  const hasOptions = sources.length > 0;
  const mutationLocked = Boolean(mutationPending) || mutationRequiresRefresh;
  useAnalysisSecondaryNavigation({
    navigationLocked: Boolean(mutationPending),
  });
  const canAdvance = currentStep === 1
    ? Boolean(setup.recordId)
    : currentStep === 2
      ? Boolean(setup.sourcePreview?.ready) && !sourceScanning
      : true;

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
    if (sourceScanError) showNotification(sourceScanError, "error");
  }, [sourceScanError, showNotification]);

  useEffect(() => {
    const errors = Array.isArray(setup.sourcePreview?.errors)
      ? setup.sourcePreview.errors
      : [];
    const warnings = Array.isArray(setup.sourcePreview?.warnings)
      ? setup.sourcePreview.warnings
      : [];

    for (const message of errors) {
      showNotification(message, "error");
    }
    for (const message of warnings) {
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
          scanProgress={sourceScanProgress}
          scanError={sourceScanError}
          onRescan={retrySourceScan}
          onCancelScan={cancelSourceScan}
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
          onChange={updateParameter}
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

  async function handleStart() {
    const run = await startRun();
    if (run?.analysis_id) {
      router.push(`/analysis/${encodeURIComponent(run.analysis_id)}`);
    }
  }

  function finalActions() {
    if (!createdRun || ["draft", "ready"].includes(createdRun.status)) {
      return (
        <Button
          className="ml-auto"
          variant="primary"
          disabled={mutationLocked}
          onClick={() => void handleStart()}
        >
          <FiPlay
            className="size-4 shrink-0"
            aria-hidden="true"
          />
          {mutationPending === "start" ? "啟動中…" : "開始分析"}
        </Button>
      );
    }

    return null;
  }

  return (
    <div className="mx-auto grid w-full max-w-7xl gap-4 pt-24 max-[980px]:pt-32">
        <Panel aria-label="新增分析">
          <PanelHeader title="新增分析" />

          <div className="grid gap-5 p-5 max-sm:p-4">
            {loading && !hasOptions ? (
              <div
                className="grid min-h-36 place-items-center rounded-xl border border-white/15 bg-black/15 p-4 text-sm font-semibold text-neutral-400"
                role="status"
              >
                讀取分析選項中…
              </div>
            ) : null}

            {loadError ? (
              <RetryMessage
                message={loadError}
                onRetry={() => void loadOptions()}
                retrying={loading}
              />
            ) : null}

            {(!loadError || hasOptions) && (!loading || hasOptions) ? (
              <>
                <AnalysisSetupProgress
                  currentStep={currentStep}
                  highestStep={highestStep}
                  locked={Boolean(createdRun) || mutationLocked}
                  onStepChange={goToStep}
                />

                {renderStep()}

                {!mutationRequiresRefresh ? (
                  <ActionRow className="w-full">
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
                          disabled={!canAdvance || mutationLocked}
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
                  </ActionRow>
                ) : null}
              </>
            ) : null}
          </div>
        </Panel>
    </div>
  );
}

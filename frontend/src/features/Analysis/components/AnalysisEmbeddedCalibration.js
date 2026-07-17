"use client";

import {
  useEffect,
  useRef,
  useState,
} from "react";
import {
  FiPlus,
  FiX,
} from "react-icons/fi";

import Button from "@/components/buttons/Button";
import RetryMessage from "@/components/feedback/RetryMessage";
import CalibrationCreateForm from "@/features/Calibration/components/CalibrationCreateForm";
import CalibrationWorkflowActions from "@/features/Calibration/components/CalibrationWorkflowActions";
import useCalibrationCatalog from "@/features/Calibration/hooks/useCalibrationCatalog";
import { runCalibrationStep } from "@/features/Calibration/lib/calibrationApiUtils";
import { messageFromError } from "@/lib/httpUtils";

export default function AnalysisEmbeddedCalibration({
  onProfileChange,
  onSelect,
}) {
  const [open, setOpen] = useState(false);
  const [profile, setProfile] = useState(null);
  const [pendingStep, setPendingStep] = useState("");
  const [workflowError, setWorkflowError] = useState("");
  const stepControllerRef = useRef(null);
  const catalog = useCalibrationCatalog();

  useEffect(() => () => {
    stepControllerRef.current?.abort();
    stepControllerRef.current = null;
  }, []);

  function closeWorkflow() {
    stepControllerRef.current?.abort();
    stepControllerRef.current = null;
    setPendingStep("");
    setWorkflowError("");
    setOpen(false);
  }

  async function handleCreate(payload) {
    const created = await catalog.create(payload);
    if (!created) return;
    setProfile(created);
    onProfileChange(created);
  }

  async function runStep(step) {
    if (!profile?.calibration_id || pendingStep) return;
    stepControllerRef.current?.abort();
    const controller = new AbortController();
    stepControllerRef.current = controller;
    setPendingStep(step);
    setWorkflowError("");
    try {
      const updated = await runCalibrationStep(
        profile.calibration_id,
        step,
        controller.signal,
      );
      if (controller.signal.aborted) return;
      setProfile(updated);
      onProfileChange(updated);
      if (updated.valid) onSelect(updated.calibration_id);
    } catch (error) {
      if (error?.name !== "AbortError") {
        setWorkflowError(messageFromError(
          error,
          "執行校正步驟失敗，請清除錯誤後重試。",
        ));
      }
    } finally {
      if (stepControllerRef.current === controller) {
        stepControllerRef.current = null;
        setPendingStep("");
      }
    }
  }

  if (!open) {
    return (
      <Button onClick={() => setOpen(true)}>
        <FiPlus
          className="size-4 shrink-0"
          aria-hidden="true"
        />
        建立新校正
      </Button>
    );
  }

  return (
    <div className="grid gap-4 rounded-[22px] border border-white/10 bg-black/10 p-4">
      <div className="flex justify-end">
        <Button onClick={closeWorkflow}>
          <FiX
            className="size-4 shrink-0"
            aria-hidden="true"
          />
          收合建立流程
        </Button>
      </div>

      {catalog.loadError ? (
        <RetryMessage
          message={catalog.loadError}
          retrying={catalog.loading}
          onRetry={() => void catalog.load()}
        />
      ) : null}

      {!profile ? (
        <CalibrationCreateForm
          sourceImages={catalog.sourceImages}
          pending={catalog.createPending}
          error={catalog.createError}
          requiresRefresh={catalog.createRequiresRefresh}
          onCreate={handleCreate}
          onClearError={catalog.clearCreateError}
          onRefresh={() => void catalog.load()}
        />
      ) : (
        <>
          {workflowError ? (
            <RetryMessage
              message={workflowError}
              onRetry={() => setWorkflowError("")}
              retryLabel="清除錯誤"
            />
          ) : null}
          <CalibrationWorkflowActions
            profile={profile}
            pending={pendingStep}
            requiresRefresh={false}
            onRun={(step) => void runStep(step)}
          />
        </>
      )}
    </div>
  );
}

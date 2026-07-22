"use client";

import {
  useEffect,
  useRef,
  useState,
} from "react";
import {
  FiCamera,
  FiCheck,
  FiSave,
  FiStopCircle,
} from "react-icons/fi";

import ActionRow from "@/components/actions/ActionRow";
import Button from "@/components/buttons/Button";
import InformationGrid from "@/components/data/InformationGrid";
import { SelectInput } from "@/components/inputs/Input";
import CameraStream from "@/components/media/CameraStream";
import InnerPanel from "@/components/panels/InnerPanel";
import { StatusPill } from "@/components/panels/Panel";

import { CALIBRATION_CAMERAS } from "../calibrationConfig";
import { intrinsicCaptureNotice } from "../lib/calibrationUtils";
import CalibrationCoverageMap from "./CalibrationCoverageMap";
import CalibrationStartButton from "./CalibrationStartButton";

const CAPTURE_MODE_OPTIONS = [
  {
    value: "automatic",
    label: "自動擷取",
  },
  {
    value: "manual",
    label: "手動擷取",
  },
];
const AUTOMATIC_CAPTURE_INTERVAL_MS = 1000;

function intrinsicStatus(intrinsics) {
  if (!intrinsics) {
    return {
      label: "尚未校正",
      tone: "neutral",
    };
  }
  if (intrinsics.status === "invalid") {
    return {
      label: "內參已失效",
      tone: "offline",
    };
  }
  if (intrinsics.status === "potentially_invalid") {
    return {
      label: "內參需確認",
      tone: "warning",
    };
  }
  if (["excellent", "acceptable"].includes(intrinsics.quality_status)) {
    return {
      label: "內參有效",
      tone: "success",
    };
  }
  if (intrinsics.quality_status === "failed") {
    return {
      label: "內參未通過",
      tone: "offline",
    };
  }
  return {
    label: "內參需檢查",
    tone: "warning",
  };
}

function displayError(value) {
  const number = Number(value);
  return Number.isFinite(number) ? `${number.toFixed(3)} px` : "—";
}

function CalibrationIntrinsicCard({
  camera,
  cameraStatus,
  detection,
  boardProfileId,
  intrinsics,
  run,
  locked,
  pendingAction,
  systemActive,
  lockedByAnotherOperator,
  startDisabled,
  onAction,
  onBeginCalibration,
  onEndCalibration,
  onStopCalibration,
  onNotify,
  onRememberRun,
}) {
  const [captureMode, setCaptureMode] = useState("automatic");
  const lastCaptureNoticeRef = useRef("");
  const coverageReady = Boolean(run?.coverage?.ready);
  const selectedResult = run?.selected_result;
  const enabled = cameraStatus?.enabled ?? true;
  const connected = Boolean(cameraStatus?.connected);
  const currentIntrinsicStatus = intrinsicStatus(intrinsics);
  const solveAction = `intrinsic.solve.${camera.id}`;
  const calculating = pendingAction === solveAction;
  const resumedActionDisabled = Boolean(
    lockedByAnotherOperator
    || startDisabled
    || pendingAction,
  );
  const intrinsicInformation = [
    {
      label: "模型",
      value: intrinsics?.camera_model || "尚無資料",
      tone: intrinsics ? "success" : "neutral",
      truncate: true,
    },
    {
      label: "解析度",
      value: intrinsics?.width && intrinsics?.height
        ? `${intrinsics.width} × ${intrinsics.height}`
        : "尚無資料",
      tone: intrinsics ? "success" : "neutral",
      truncate: true,
    },
    {
      label: "誤差",
      value: intrinsics
        ? displayError(intrinsics.reprojection_error_px)
        : "尚無資料",
      tone: intrinsics ? "success" : "neutral",
      truncate: true,
    },
  ];

  async function runAction(
    action,
    path,
    options,
  ) {
    const outcome = await onAction(action, path, options);
    if (outcome?.result?.run_id) {
      onRememberRun(camera.id, outcome.result);
    }
    return outcome;
  }

  async function ensureCalibrationLock() {
    if (locked) return true;
    const outcome = await onBeginCalibration(
      "intrinsic",
      {
        run_id: run?.run_id,
      },
    );
    return Boolean(outcome);
  }

  async function captureSample({
    acquireLock = false,
  } = {}) {
    if (!run?.run_id) return null;
    if (acquireLock && !(await ensureCalibrationLock())) return null;
    const outcome = await runAction(
      `intrinsic.capture.${camera.id}`,
      `/api/calibration/intrinsics/${camera.id}/capture`,
      {
        body: {
          run_id: run.run_id,
        },
        refresh: false,
      },
    );
    const notice = intrinsicCaptureNotice(camera.label, outcome?.result);
    if (notice && notice.message !== lastCaptureNoticeRef.current) {
      lastCaptureNoticeRef.current = notice.message;
      onNotify(notice.message, notice.tone);
    }
    return outcome;
  }

  async function solveCalibration() {
    if (!(await ensureCalibrationLock())) return null;
    return runAction(
      solveAction,
      `/api/calibration/intrinsics/${camera.id}/solve`,
      {
        body: {
          run_id: run.run_id,
        },
        timeoutMs: 180_000,
        successMessage: `${camera.label}內參計算完成。`,
      },
    );
  }

  async function applyCalibration() {
    if (!(await ensureCalibrationLock())) return null;
    const outcome = await onAction(
      `intrinsic.apply.${camera.id}`,
      `/api/calibration/intrinsics/${camera.id}/apply`,
      {
        body: {
          run_id: run.run_id,
        },
        timeoutMs: 180_000,
        successMessage: `${camera.label}內參已更新。`,
      },
    );
    if (outcome) {
      onRememberRun(camera.id, null);
      await onEndCalibration();
    }
    return outcome;
  }

  async function startCalibration() {
    const lockOutcome = await onBeginCalibration("intrinsic");
    if (!lockOutcome) return;

    const outcome = await runAction(
      `intrinsic.create.${camera.id}`,
      `/api/calibration/intrinsics/${camera.id}/runs`,
      {
        body: {
          board_profile_id: boardProfileId,
          capture_mode: captureMode,
          camera_model: "auto",
          minimum_interval_seconds: AUTOMATIC_CAPTURE_INTERVAL_MS / 1000,
        },
        successMessage: `已開始${camera.label}內參校正。`,
      },
    );

    if (!outcome && lockOutcome.acquired) {
      await onEndCalibration(true);
    }
  }

  useEffect(() => {
    if (
      !locked
      || run?.capture_mode !== "automatic"
      || !["capturing", "ready"].includes(run?.status)
    ) {
      return undefined;
    }

    const intervalId = window.setInterval(() => {
      if (
        !pendingAction
        && detection?.capture_ready
        && document.visibilityState === "visible"
      ) {
        void captureSample();
      }
    }, AUTOMATIC_CAPTURE_INTERVAL_MS);
    return () => window.clearInterval(intervalId);
  }, [
    detection?.capture_ready,
    locked,
    pendingAction,
    run?.capture_mode,
    run?.run_id,
    run?.status,
  ]);

  return (
    <InnerPanel
      as="article"
      className="content-start gap-0 overflow-hidden p-0!"
    >
      <CameraStream
        cameraId={camera.id}
        label={camera.label}
        device={camera.device}
        enabled={enabled}
        connected={connected}
        actualFps={cameraStatus?.actual_fps}
        calibrated={intrinsics?.status === "valid"}
        streamPath={boardProfileId
          ? `/api/calibration/cameras/${camera.id}/stream?board_profile_id=${encodeURIComponent(boardProfileId)}`
          : undefined
        }
        onNotify={onNotify}
      />

      <div className="grid gap-6 border-t border-white/15 p-4">
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          <StatusPill tone={connected ? "success" : "offline"}>
            {connected ? "已連線" : "離線"}
          </StatusPill>
          <StatusPill tone={detection?.board_detected ? "success" : "neutral"}>
            {detection?.board_detected ? "已辨識校正板" : "未辨識校正板"}
          </StatusPill>
          <StatusPill tone={currentIntrinsicStatus.tone}>
            {currentIntrinsicStatus.label}
          </StatusPill>
          <div className="flex min-w-0 flex-wrap items-center gap-2 text-xs">
            {run ? (
              <StatusPill tone={coverageReady ? "success" : "warning"}>
                {coverageReady ? "樣本已足夠" : "收集樣本中"}
              </StatusPill>
            ) : null}
            {selectedResult ? (
              <span className="font-bold text-neutral-300">
                驗證誤差 {displayError(selectedResult.validation_error_px)}
              </span>
            ) : null}
          </div>
        </div>


        <InformationGrid
          items={intrinsicInformation}
          columns={3}
          border="none"
        />

        {!run ? (
          <div className="flex flex-col gap-3">
            <ActionRow
              className="flex flex-row gap-3 items-center justify-center"
              dividerClassName="my-0!"
            >
              <div className="min-w-32">
                <SelectInput
                  id={`calibration-${camera.id}-capture-mode`}
                  label="擷取方式"
                  value={captureMode}
                  options={CAPTURE_MODE_OPTIONS}
                  onValueChange={setCaptureMode}
                />
              </div>

              <CalibrationStartButton
                disabled={lockedByAnotherOperator || startDisabled || !connected || !boardProfileId || Boolean(pendingAction)}
                systemActive={systemActive}
                onClick={() => void startCalibration()}
              />
            </ActionRow>
          </div>
        ) : (
          <>
            <CalibrationCoverageMap run={run} />

            <div className="flex flex-col gap-3">
              <ActionRow
                className="flex flex-row gap-3 items-center justify-center"
                dividerClassName="my-0!"
              >
                <Button
                  disabled={!connected || resumedActionDisabled}
                  onClick={() => void captureSample({
                    acquireLock: true,
                  })}
                >
                  <FiCamera
                    className="size-4 shrink-0"
                    aria-hidden="true"
                  />
                  擷取樣本
                </Button>
                <Button
                  disabled={!coverageReady || resumedActionDisabled}
                  onClick={() => void solveCalibration()}
                >
                  <FiCheck
                    className="size-4 shrink-0"
                    aria-hidden="true"
                  />
                  {calculating ? "計算中…" : "計算"}
                </Button>
                <Button
                  variant="primary"
                  disabled={
                    run.status !== "solved"
                    || resumedActionDisabled
                  }
                  onClick={() => void applyCalibration()}
                >
                  <FiSave
                    className="size-4 shrink-0"
                    aria-hidden="true"
                  />
                  套用
                </Button>
                <Button
                  variant="danger"
                  onClick={() => void onStopCalibration(
                    camera.id,
                    run.run_id,
                  )}
                >
                  <FiStopCircle
                    className="size-4 shrink-0"
                    aria-hidden="true"
                  />
                  停止校正
                </Button>
              </ActionRow>
            </div>
          </>
        )}
      </div>
    </InnerPanel>
  );
}

export default function CalibrationIntrinsics({
  status,
  runs,
  boardProfileId,
  locked,
  pendingAction,
  systemActive,
  lockedByAnotherOperator,
  startDisabled,
  onAction,
  onBeginCalibration,
  onEndCalibration,
  onStopCalibration,
  onNotify,
  onRememberRun,
}) {
  const cameraStatuses = new Map(
    (status?.cameras || []).map((camera) => [camera.camera_id, camera]),
  );
  const intrinsics = new Map(
    (status?.intrinsics || []).map((item) => [item.camera_id, item]),
  );

  return (
    <div className="grid gap-3 min-[720px]:grid-cols-2 min-[1180px]:grid-cols-3">
      {CALIBRATION_CAMERAS.map((camera) => (
        <CalibrationIntrinsicCard
          camera={camera}
          cameraStatus={cameraStatuses.get(camera.id)}
          detection={status?.detections?.[camera.id]}
          boardProfileId={boardProfileId}
          intrinsics={intrinsics.get(camera.id)}
          run={runs[camera.id]}
          locked={locked}
          pendingAction={pendingAction}
          systemActive={systemActive}
          lockedByAnotherOperator={lockedByAnotherOperator}
          startDisabled={startDisabled}
          onAction={onAction}
          onBeginCalibration={onBeginCalibration}
          onEndCalibration={onEndCalibration}
          onStopCalibration={onStopCalibration}
          onNotify={onNotify}
          onRememberRun={onRememberRun}
          key={camera.id}
        />
      ))}
    </div>
  );
}

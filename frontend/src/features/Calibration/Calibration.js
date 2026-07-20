"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useState,
} from "react";

import {
  Panel,
  PanelHeader,
} from "@/components/panels/Panel";
import MainNavigation from "@/features/MainNavigation/MainNavigation";
import useNotificationsContext from "@/features/Notifications/hooks/useNotificationsContext";

import CalibrationBoardSettings from "./components/CalibrationBoardSettings";
import CalibrationExtrinsics from "./components/CalibrationExtrinsics";
import CalibrationExtrinsicStatus from "./components/CalibrationExtrinsicStatus";
import CalibrationIntrinsics from "./components/CalibrationIntrinsics";
import CalibrationMotorControls from "./components/CalibrationMotorControls";
import useUnifiedCalibration from "./hooks/useUnifiedCalibration";
import { calibrationLockState } from "./lib/calibrationUtils";

export default function Calibration() {
  const { showNotification } = useNotificationsContext();
  const [selectedBoardId, setSelectedBoardId] = useState("");
  const [selectedProfileId, setSelectedProfileId] = useState("");
  const {
    status,
    boards,
    profiles,
    runs,
    loading,
    pendingAction,
    error,
    requiresRefresh,
    ownsLock,
    systemActive,
    mutate,
    acquireLock,
    releaseLock,
    rememberRun,
    clearError,
    connection,
    socketError,
    resetSocketError,
  } = useUnifiedCalibration({
    polling: true,
  });

  useEffect(() => {
    if (selectedBoardId && boards.some(
      (board) => board.board_profile_id === selectedBoardId,
    )) {
      return;
    }
    setSelectedBoardId(
      boards.at(-1)?.board_profile_id
        || "",
    );
  }, [
    boards,
    selectedBoardId,
  ]);

  useEffect(() => {
    if (!error) return;
    showNotification(error, "error");
    clearError();
  }, [
    clearError,
    error,
    showNotification,
  ]);

  useEffect(() => {
    if (!socketError) return;
    showNotification(
      `${socketError.message} 校正狀態仍會定時重新讀取。`,
      "error",
    );
    resetSocketError();
  }, [
    resetSocketError,
    showNotification,
    socketError,
  ]);

  const onAction = useCallback(async (
    action,
    path,
    options,
  ) => {
    const outcome = await mutate(action, path, options);
    if (outcome?.successMessage) {
      showNotification(outcome.successMessage, "success");
    }
    return outcome;
  }, [
    mutate,
    showNotification,
  ]);

  const selectedProfile = useMemo(() => profiles.find(
    (profile) => profile.profile_id === selectedProfileId,
  ) || null, [
    profiles,
    selectedProfileId,
  ]);
  const lockState = calibrationLockState(status, ownsLock);
  const lockedByAnotherOperator = lockState.lockedByAnotherOperator;
  const lockMode = status?.lock?.mode;
  const intrinsicLocked = ownsLock && [
    "intrinsic",
    "unified",
  ].includes(lockMode);
  const extrinsicLocked = ownsLock && [
    "extrinsic",
    "relocation",
    "unified",
  ].includes(lockMode);
  const hasWorkspace = Boolean(status) || boards.length > 0 || profiles.length > 0;

  const beginCalibration = useCallback(async (
    mode,
    details = {},
  ) => {
    if (systemActive) {
      showNotification(
        "目前系統運行中無法校正",
        "warning",
      );
      return null;
    }

    if (ownsLock) {
      return {
        acquired: false,
      };
    }

    const outcome = await acquireLock(mode, details);
    if (outcome?.successMessage) {
      showNotification(outcome.successMessage, "success");
    }

    return outcome
      ? {
        acquired: true,
      }
      : null;
  }, [
    acquireLock,
    ownsLock,
    showNotification,
    systemActive,
  ]);

  const endCalibration = useCallback(async (
    releaseAcquiredLock = false,
  ) => {
    if (!ownsLock && !releaseAcquiredLock) return true;
    const outcome = await releaseLock();
    if (outcome?.successMessage) {
      showNotification(outcome.successMessage, "success");
    }
    return Boolean(outcome);
  }, [
    ownsLock,
    releaseLock,
    showNotification,
  ]);

  return (
    <main className="min-h-screen bg-[#06100c] px-5 pb-8 max-sm:px-3">
      <MainNavigation isConnected={connection === "connected"} />

      <div className="mx-auto grid w-full max-w-[112.5rem] gap-4 pt-[5.6rem] max-[980px]:pt-[8.8rem]">
        <Panel aria-label="校正板">
          <PanelHeader title="校正板" />

          <div className="grid gap-4 p-5 max-sm:p-4">
            {loading && !hasWorkspace ? (
              <div
                className="grid min-h-36 place-items-center rounded-xl border border-white/10 bg-black/10 p-4 text-sm font-semibold text-neutral-400"
                role="status"
              >
                讀取校正板設定中…
              </div>
            ) : null}

            {hasWorkspace ? (
              <CalibrationBoardSettings
                boards={boards}
                selectedBoardId={selectedBoardId}
                pendingAction={pendingAction}
                onBoardChange={setSelectedBoardId}
                onAction={onAction}
              />
            ) : null}
          </div>
        </Panel>

        <Panel aria-label="內部參數">
          <PanelHeader title="內部參數" />

          <div className="p-5 max-sm:p-4">
            {hasWorkspace ? (
              <CalibrationIntrinsics
                status={status}
                runs={runs}
                boardProfileId={selectedBoardId}
                locked={intrinsicLocked}
                pendingAction={pendingAction}
                systemActive={systemActive}
                lockedByAnotherOperator={lockedByAnotherOperator}
                startDisabled={requiresRefresh}
                onAction={onAction}
                onBeginCalibration={beginCalibration}
                onEndCalibration={endCalibration}
                onNotify={showNotification}
                onRememberRun={rememberRun}
              />
            ) : null}
          </div>
        </Panel>

        <Panel aria-label="外部參數">
          <PanelHeader title="外部參數" />

          <div className="grid gap-6 p-5 max-sm:p-4">
            {hasWorkspace ? (
              <>
                <CalibrationExtrinsicStatus
                  status={status}
                  locked={extrinsicLocked}
                  pendingAction={pendingAction}
                  onAction={onAction}
                />

                <hr />

                <CalibrationMotorControls
                  status={status}
                  profile={selectedProfile}
                  locked={extrinsicLocked}
                  pendingAction={pendingAction}
                  onAction={onAction}
                />

                <hr />

                <CalibrationExtrinsics
                  selectedBoardId={selectedBoardId}
                  profiles={profiles}
                  status={status}
                  locked={extrinsicLocked}
                  pendingAction={pendingAction}
                  systemActive={systemActive}
                  lockedByAnotherOperator={lockedByAnotherOperator}
                  startDisabled={requiresRefresh}
                  selectedProfileId={selectedProfileId}
                  onSelectedProfileChange={setSelectedProfileId}
                  onAction={onAction}
                  onBeginCalibration={beginCalibration}
                  onEndCalibration={endCalibration}
                  onNotify={showNotification}
                />
              </>
            ) : null}
          </div>
        </Panel>
      </div>
    </main>
  );
}

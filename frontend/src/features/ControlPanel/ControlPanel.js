"use client";

import {
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";

import ImagePreview from "@/features/ImagePreview/ImagePreview";
import { IMAGE_PREVIEW_META } from "@/features/ImagePreview/imagePreviewConfig";
import Control from "@/features/Control/Control";
import MainNavigation from "@/features/MainNavigation/MainNavigation";
import { CAPTURE_SECONDARY_NAVIGATION_ITEMS } from "@/features/MainNavigation/mainNavigationConfig";
import Notifications from "@/features/Notifications/Notifications";
import useNotifications from "@/features/Notifications/hooks/useNotifications";
import RecordsStorage from "@/features/RecordsStorage/RecordsStorage";
import useRecordsStorage from "@/features/RecordsStorage/hooks/useRecordsStorage";
import Schedule from "@/features/Schedule/Schedule";
import SystemStatus from "@/features/SystemStatus/SystemStatus";
import usePhytoSocket from "@/hooks/usePhytoSocket";
import {
  messageFromError,
  parseJsonResponse,
  responseErrorMessage,
} from "@/lib/httpUtils";

import { executeControlPanelAction } from "./lib/controlPanelUtils";

export default function ControlPanel() {
  const {
    snapshot,
    connection,
    socketError,
    authExpired,
    command,
  } = usePhytoSocket();
  const {
    toast,
    notifications,
    showNotification,
    dismissNotification,
    clearNotifications,
  } = useNotifications(snapshot?.system?.recent_errors);
  const [busyActions, setBusyActions] = useState(() => new Set());
  const [logoutPending, setLogoutPending] = useState(false);
  const [openSettingsGroups, setOpenSettingsGroups] = useState([]);
  const mountedRef = useRef(false);
  const pendingActionsRef = useRef(new Map());
  const logoutPendingRef = useRef(false);
  const previousScheduleActiveRef = useRef(false);
  const {
    records,
    loading: recordsLoading,
    loadError: recordsLoadError,
    loadRecords,
  } = useRecordsStorage({
    onNotify: showNotification,
  });

  useEffect(() => {
    mountedRef.current = true;

    return () => {
      mountedRef.current = false;
    };
  }, []);

  useEffect(() => {
    if (!socketError) return;

    showNotification(socketError.message, "error");
  }, [
    showNotification,
    socketError,
  ]);

  useEffect(() => {
    if (authExpired) {
      window.location.replace("/");
    }
  }, [authExpired]);

  const runAction = useCallback((
    action,
    payload = {},
    successMessage,
  ) => {
    const existingRequest = pendingActionsRef.current.get(action);

    if (existingRequest) return existingRequest;

    let request;

    request = (async () => {
      try {
        const result = await executeControlPanelAction({
          action,
          payload,
          command,
        });

        if (successMessage && mountedRef.current) {
          showNotification(successMessage, "success");
        }

        return result;
      } catch (error) {
        if (error?.code !== "operation_cancelled" && mountedRef.current) {
          showNotification(messageFromError(error, "操作失敗。"), "error");
        }

        return null;
      } finally {
        if (pendingActionsRef.current.get(action) === request) {
          pendingActionsRef.current.delete(action);

          if (mountedRef.current) {
            setBusyActions(new Set(pendingActionsRef.current.keys()));
          }
        }
      }
    })();

    pendingActionsRef.current.set(action, request);
    setBusyActions(new Set(pendingActionsRef.current.keys()));
    return request;
  }, [command, showNotification]);

  async function logout() {
    if (logoutPendingRef.current) return;

    logoutPendingRef.current = true;
    setLogoutPending(true);

    try {
      const response = await fetch("/api/auth/logout", {
        method: "POST",
      });
      const payload = await parseJsonResponse(response);

      if (!response.ok) {
        throw new Error(responseErrorMessage(
          payload,
          "登出失敗，請稍後重試。",
        ));
      }

      window.location.assign("/");
    } catch (error) {
      if (mountedRef.current) {
        showNotification(messageFromError(error, "登出失敗，請稍後重試。"), "error");
      }
    } finally {
      logoutPendingRef.current = false;

      if (mountedRef.current) {
        setLogoutPending(false);
      }
    }
  }

  const clearNotificationErrors = useCallback(async () => {
    const result = await runAction("system.errors.reset");

    if (result !== null) {
      clearNotifications();
    }
  }, [clearNotifications, runAction]);

  function toggleSettings(group) {
    setOpenSettingsGroups((current) => (
      current.includes(group)
        ? current.filter((currentGroup) => currentGroup !== group)
        : [...current, group]
    ));
  }

  const isConnected = connection === "connected";
  const system = snapshot?.system || {};
  const motor = snapshot?.motor || {};
  const scheduleStatus = snapshot?.schedule || {};
  const cameras = snapshot?.cameras || [];
  const imagePreviewById = new Map(cameras.map((camera) => [camera.camera_id, camera]));
  const scheduleActive = ["running", "paused", "stopping"].includes(scheduleStatus.status);

  useEffect(() => {
    const wasActive = previousScheduleActiveRef.current;
    previousScheduleActiveRef.current = scheduleActive;

    if (wasActive && !scheduleActive) {
      void loadRecords({ queueIfBusy: true });
    }
  }, [loadRecords, scheduleActive]);

  return (
    <main className="min-h-screen bg-[#06100c] px-5 pb-8 max-sm:px-3">
      <MainNavigation
        isConnected={isConnected}
        emergencyStopping={busyActions.has("motor.emergency_stop")}
        logoutPending={logoutPending}
        onEmergencyStop={() => void runAction(
          "motor.emergency_stop",
          {},
          "已送出緊急停止命令。",
        )}
        onLogout={() => void logout()}
        secondaryItems={CAPTURE_SECONDARY_NAVIGATION_ITEMS}
      />

      <div className="mx-auto grid w-full max-w-[112.5rem] gap-4 pt-[8.75rem] min-[981px]:grid-cols-[minmax(0,1fr)_minmax(18.75rem,22.5rem)] max-[980px]:pt-[11.5rem]">
        <ImagePreview
          imagePreviewById={imagePreviewById}
          busyActions={busyActions}
          scheduleActive={scheduleActive}
          open={openSettingsGroups.includes("cameras")}
          onToggle={() => toggleSettings("cameras")}
          onRunAction={runAction}
          onNotify={showNotification}
        />
        <aside className="grid min-w-0 gap-4 min-[981px]:col-start-2 min-[981px]:row-start-2 min-[981px]:row-span-4 min-[981px]:sticky min-[981px]:top-[5.65rem] min-[981px]:self-start" aria-label="狀態列">
          <SystemStatus
            imagePreviewMeta={IMAGE_PREVIEW_META}
            imagePreviewById={imagePreviewById}
            connection={connection}
            schedule={scheduleStatus}
            system={system}
          />
        </aside>
        <Schedule
          scheduleStatus={scheduleStatus}
          motor={motor}
          isConnected={isConnected}
          busyActions={busyActions}
          scheduleActive={scheduleActive}
          open={openSettingsGroups.includes("schedule")}
          onToggle={() => toggleSettings("schedule")}
          onNotify={showNotification}
          onRunAction={runAction}
          onStarted={loadRecords}
        />
        <Control
          motor={motor}
          isConnected={isConnected}
          busyActions={busyActions}
          scheduleActive={scheduleActive}
          open={openSettingsGroups.includes("motor")}
          onToggle={() => toggleSettings("motor")}
          onNotify={showNotification}
          onRunAction={runAction}
        />
        <RecordsStorage
          records={records}
          loading={recordsLoading}
          loadError={recordsLoadError}
          scheduleActive={scheduleActive}
          open={openSettingsGroups.includes("records-storage")}
          onToggle={() => toggleSettings("records-storage")}
          onNotify={showNotification}
          onLoad={loadRecords}
        />
      </div>
      <Notifications
        toast={toast}
        notifications={notifications}
        clearing={busyActions.has("system.errors.reset")}
        clearDisabled={!isConnected}
        onClear={() => void clearNotificationErrors()}
        onClose={dismissNotification}
      />
    </main>
  );
}

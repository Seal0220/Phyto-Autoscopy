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
import useNotificationsContext from "@/features/Notifications/hooks/useNotificationsContext";
import RecordsStorage from "@/features/RecordsStorage/RecordsStorage";
import useRecordsStorage from "@/features/RecordsStorage/hooks/useRecordsStorage";
import Schedule from "@/features/Schedule/Schedule";
import SystemStatus from "@/features/SystemStatus/SystemStatus";
import { usePhytoSocketContext } from "@/hooks/PhytoSocketProvider";
import {
  messageFromError,
} from "@/lib/httpUtils";

import { executeControlPanelAction } from "./lib/controlPanelUtils";

export default function ControlPanel() {
  const {
    snapshot,
    connection,
    socketError,
    command,
  } = usePhytoSocketContext();
  const {
    showNotification,
    syncRecentErrors,
  } = useNotificationsContext();
  const [busyActions, setBusyActions] = useState(() => new Set());
  const [openSettingsGroups, setOpenSettingsGroups] = useState([
    "cameras",
  ]);
  const mountedRef = useRef(false);
  const pendingActionsRef = useRef(new Map());
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
    syncRecentErrors(snapshot?.system?.recent_errors);
  }, [
    snapshot?.system?.recent_errors,
    syncRecentErrors,
  ]);

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
    <div className="mx-auto grid w-full max-w-[112.5rem] gap-4 pt-35 min-[981px]:grid-cols-[minmax(0,1fr)_minmax(18.75rem,22.5rem)] max-[980px]:pt-46">
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
            motor={motor}
            schedule={scheduleStatus}
            system={system}
          />
        </aside>

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

        <Schedule
          scheduleStatus={scheduleStatus}
          motor={motor}
          isConnected={isConnected}
          busyActions={busyActions}
          scheduleActive={scheduleActive}
          onNotify={showNotification}
          onRunAction={runAction}
          onStarted={loadRecords}
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
  );
}

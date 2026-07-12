"use client";

import {
  useCallback,
  useState,
} from "react";

import ImagePreview from "@/features/ImagePreview/ImagePreview";
import { IMAGE_PREVIEW_META } from "@/features/ImagePreview/imagePreviewConfig";
import Header from "@/features/Dashboard/components/Header";
import Motor from "@/features/Motor/Motor";
import ToastViewport from "@/features/Notifications/ToastViewport";
import useNotifications from "@/features/Notifications/hooks/useNotifications";
import RecordsStorage from "@/features/RecordsStorage/RecordsStorage";
import useRecordsStorage from "@/features/RecordsStorage/hooks/useRecordsStorage";
import Schedule from "@/features/Schedule/Schedule";
import Status from "@/features/Status/Status";
import usePhytoSocket from "@/hooks/usePhytoSocket";
import { messageFromError } from "@/lib/httpUtils";

export default function Dashboard({ actor }) {
  const { snapshot, connection, command } = usePhytoSocket();
  const {
    toast,
    notifications,
    showNotification,
    dismissNotification,
  } = useNotifications(snapshot?.system?.recent_errors);
  const [busyAction, setBusyAction] = useState("");
  const [openSettingsGroups, setOpenSettingsGroups] = useState([]);
  const {
    records,
    loading: recordsLoading,
    loadRecords,
  } = useRecordsStorage({
    onNotify: showNotification,
  });

  const runAction = useCallback(async (action, payload = {}, successMessage) => {
    setBusyAction(action);
    try {
      const result = await command(action, payload);
      if (successMessage) showNotification(successMessage, "success");
      return result;
    } catch (error) {
      showNotification(messageFromError(error, "操作失敗。"), "error");
      return null;
    } finally {
      setBusyAction("");
    }
  }, [command, showNotification]);

  async function logout() {
    await fetch("/api/auth/logout", { method: "POST" });
    window.location.assign("/");
  }

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
  const experiment = snapshot?.experiment || {};
  const cameras = snapshot?.cameras || [];
  const imagePreviewById = new Map(cameras.map((camera) => [camera.camera_id, camera]));
  const scheduleActive = ["running", "paused", "stopping"].includes(experiment.status);
  const activeRecord = records.find((record) => record.session_id === experiment.session_id);

  return (
    <main className="min-h-screen bg-[#06100c] px-5 pb-8 max-sm:px-3">
      <Header
        actor={actor}
        isConnected={isConnected}
        emergencyStopping={busyAction === "motor.emergency_stop"}
        onEmergencyStop={() => void runAction("motor.emergency_stop", {}, "已送出緊急停止命令。")}
        onLogout={() => void logout()}
      />

      <div className="mx-auto grid w-full max-w-[112.5rem] gap-4 pt-[5.6rem] min-[981px]:grid-cols-[minmax(0,1fr)_minmax(18.75rem,22.5rem)] max-[980px]:pt-[8.8rem]">
        <ImagePreview
          imagePreviewById={imagePreviewById}
          isConnected={isConnected}
          busyAction={busyAction}
          scheduleActive={scheduleActive}
          open={openSettingsGroups.includes("cameras")}
          onToggle={() => toggleSettings("cameras")}
          onRunAction={runAction}
          onNotify={showNotification}
        />
        <aside className="grid min-w-0 gap-4 min-[981px]:col-start-2 min-[981px]:row-start-2 min-[981px]:row-span-3 min-[981px]:sticky min-[981px]:top-[5.65rem] min-[981px]:self-start" aria-label="狀態列">
          <Status
            imagePreviewMeta={IMAGE_PREVIEW_META}
            imagePreviewById={imagePreviewById}
            connection={connection}
            experiment={experiment}
            system={system}
          />
        </aside>
        <Schedule
          experiment={experiment}
          isConnected={isConnected}
          busyAction={busyAction}
          scheduleActive={scheduleActive}
          open={openSettingsGroups.includes("experiment")}
          onToggle={() => toggleSettings("experiment")}
          onNotify={showNotification}
          onRunAction={runAction}
          onStarted={loadRecords}
        />
        <Motor
          motor={motor}
          isConnected={isConnected}
          busyAction={busyAction}
          scheduleActive={scheduleActive}
          open={openSettingsGroups.includes("motor")}
          onToggle={() => toggleSettings("motor")}
          onNotify={showNotification}
          onRunAction={runAction}
        />
        <RecordsStorage
          records={records}
          loading={recordsLoading}
          scheduleActive={scheduleActive}
          storageDirectory={activeRecord?.session_path}
          open={openSettingsGroups.includes("records-storage")}
          onToggle={() => toggleSettings("records-storage")}
          onNotify={showNotification}
          onLoad={loadRecords}
        />
      </div>
      <ToastViewport toast={toast} notifications={notifications} onClose={dismissNotification} />
    </main>
  );
}

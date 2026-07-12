"use client";

import { useCallback, useEffect, useState } from "react";

import DashboardHeader from "@/components/dashboard-header";
import CamerasSection from "@/components/sections/section-cameras";
import ScheduleSection from "@/components/sections/section-schedule";
import MotorSection from "@/components/sections/section-motor";
import SessionsSection from "@/components/sections/section-sessions";
import StatusSection from "@/components/sections/section-status";
import ToastViewport from "@/components/toast-viewport";
import useNotifications from "@/hooks/use-notifications";
import usePhytoSocket from "@/hooks/use-phyto-socket";
import { CAMERA_META } from "@/lib/cameras";
import { messageFromError, parseJsonResponse } from "@/lib/http";
import { buildSchedulePayload, INITIAL_SCHEDULE } from "@/lib/schedule";

export default function Dashboard({ actor }) {
  const { snapshot, connection, command } = usePhytoSocket();
  const {
    toast,
    notifications,
    showNotification,
    dismissNotification,
  } = useNotifications(snapshot?.system?.recent_errors);
  const [busyAction, setBusyAction] = useState("");
  const [schedule, setSchedule] = useState(INITIAL_SCHEDULE);
  const [sessions, setSessions] = useState([]);
  const [sessionsLoading, setSessionsLoading] = useState(false);
  const [openSettingsGroups, setOpenSettingsGroups] = useState([]);

  const loadSessions = useCallback(async () => {
    setSessionsLoading(true);
    try {
      const response = await fetch("/api/sessions", { cache: "no-store" });
      const payload = await parseJsonResponse(response);
      if (!response.ok) throw new Error(payload.detail || "讀取工作階段失敗。");
      setSessions(Array.isArray(payload) ? payload : []);
    } catch (error) {
      showNotification(messageFromError(error, "讀取工作階段失敗。"), "error");
    } finally {
      setSessionsLoading(false);
    }
  }, [showNotification]);

  useEffect(() => {
    void loadSessions();
  }, [loadSessions]);

  useEffect(() => {
    let active = true;
    async function loadScheduleDefaults() {
      try {
        const response = await fetch("/api/settings/experiment", { cache: "no-store" });
        const payload = await parseJsonResponse(response);
        if (!response.ok || !payload.experiment || !active) return;
        const experiment = payload.experiment;
        setSchedule((previous) => ({
          duration_seconds: String((experiment.duration_minutes ?? Number(INITIAL_SCHEDULE.duration_seconds) / 60) * 60),
          rotation_start_deg: String(experiment.rotation_start_deg ?? INITIAL_SCHEDULE.rotation_start_deg),
          rotation_end_deg: String(experiment.rotation_end_deg ?? INITIAL_SCHEDULE.rotation_end_deg),
          rotation_step_deg: String(experiment.rotation_step_deg ?? INITIAL_SCHEDULE.rotation_step_deg),
          angle_tolerance_deg: String(experiment.angle_tolerance_deg ?? INITIAL_SCHEDULE.angle_tolerance_deg),
          modes: previous.modes.map((mode, index) => (
            index === 0 && mode.type === "seconds_interval"
              ? { ...mode, interval_seconds: String(experiment.capture_interval_seconds ?? mode.interval_seconds) }
              : mode
          )),
        }));
      } catch {
        // Keep the live controls usable with safe defaults.
      }
    }
    void loadScheduleDefaults();
    return () => { active = false; };
  }, []);

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

  async function handleScheduleSubmit(event) {
    event.preventDefault();
    let payload;
    try {
      payload = buildSchedulePayload(schedule);
    } catch (error) {
      showNotification(messageFromError(error, "排程內容無效。"), "error");
      return;
    }
    const result = await runAction("experiment.start", payload, "排程已開始。");
    if (result) void loadSessions();
  }

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
  const cameraById = new Map(cameras.map((camera) => [camera.camera_id, camera]));
  const scheduleActive = ["running", "paused", "stopping"].includes(experiment.status);

  return (
    <main className="min-h-screen bg-[#06100c] px-5 pb-8 max-sm:px-3">
      <DashboardHeader
        actor={actor}
        isConnected={isConnected}
        emergencyStopping={busyAction === "motor.emergency_stop"}
        onEmergencyStop={() => void runAction("motor.emergency_stop", {}, "已送出緊急停止命令。")}
        onLogout={() => void logout()}
      />

      <div className="mx-auto grid w-full max-w-[112.5rem] gap-4 pt-[5.6rem] min-[981px]:grid-cols-[minmax(0,1fr)_minmax(18.75rem,22.5rem)] max-[980px]:pt-[8.8rem]">
        <CamerasSection
          cameraMeta={CAMERA_META}
          cameraById={cameraById}
          isConnected={isConnected}
          busyAction={busyAction}
          scheduleActive={scheduleActive}
          open={openSettingsGroups.includes("cameras")}
          onToggle={() => toggleSettings("cameras")}
          onRunAction={runAction}
          onNotify={showNotification}
        />
        <aside className="grid min-w-0 gap-4 min-[981px]:col-start-2 min-[981px]:row-start-2 min-[981px]:row-span-3 min-[981px]:sticky min-[981px]:top-[5.65rem] min-[981px]:self-start" aria-label="狀態列">
          <StatusSection cameraMeta={CAMERA_META} cameraById={cameraById} connection={connection} experiment={experiment} system={system} />
        </aside>
        <ScheduleSection
          experiment={experiment}
          isConnected={isConnected}
          busyAction={busyAction}
          scheduleActive={scheduleActive}
          open={openSettingsGroups.includes("experiment")}
          onToggle={() => toggleSettings("experiment")}
          onNotify={showNotification}
          onRunAction={runAction}
          schedule={schedule}
          setSchedule={setSchedule}
          onScheduleSubmit={handleScheduleSubmit}
        />
        <MotorSection
          motor={motor}
          isConnected={isConnected}
          busyAction={busyAction}
          scheduleActive={scheduleActive}
          open={openSettingsGroups.includes("motor")}
          onToggle={() => toggleSettings("motor")}
          onNotify={showNotification}
          onRunAction={runAction}
        />
        <SessionsSection
          sessions={sessions}
          loading={sessionsLoading}
          scheduleActive={scheduleActive}
          open={openSettingsGroups.includes("logging")}
          onToggle={() => toggleSettings("logging")}
          onNotify={showNotification}
          onLoad={loadSessions}
        />
      </div>
      <ToastViewport toast={toast} notifications={notifications} onClose={dismissNotification} />
    </main>
  );
}

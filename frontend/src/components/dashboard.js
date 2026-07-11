"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import CamerasSection from "@/components/sections/section-cameras";
import ExperimentSection from "@/components/sections/section-experiment";
import MotorSection from "@/components/sections/section-motor";
import RecentMessagesSection from "@/components/sections/section-recent-messages";
import SessionsSection from "@/components/sections/section-sessions";
import StatusSection from "@/components/sections/section-status";
import Button from "@/components/ui/button";
import NavLink from "@/components/ui/nav-link";
import ToastViewport from "@/components/toast-viewport";

const CAMERA_META = {
  top: { label: "頂視角", device: "CHLOROCULUS EYE-TOP" },
  fixed_side: { label: "固定側視角", device: "CHLOROCULUS EYE-SIDE" },
  rotating_arm: { label: "旋臂視角", device: "CHLOROCULUS EYE-ARM" },
};

const INITIAL_SCHEDULE = {
  capture_interval_seconds: "60",
  duration_minutes: "240",
  rotation_start_deg: "0",
  rotation_end_deg: "360",
  rotation_step_deg: "15",
};

const INITIAL_ROTATION = {
  cycle_id: "1",
  start_deg: "0",
  end_deg: "360",
  step_deg: "15",
};

function parseJson(response) {
  return response.json().catch(() => ({}));
}

function messageFrom(error, fallback) {
  return error instanceof Error && error.message ? error.message : fallback;
}

function numberPayload(values) {
  return Object.fromEntries(Object.entries(values).map(([key, value]) => [key, Number(value)]));
}

function socketUrl(ticket) {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${protocol}//${window.location.host}/ws/status?ticket=${encodeURIComponent(ticket)}`;
}

function usePhytoSocket() {
  const [snapshot, setSnapshot] = useState(null);
  const [connection, setConnection] = useState("connecting");
  const socketRef = useRef(null);
  const pendingRef = useRef(new Map());
  const counterRef = useRef(0);

  useEffect(() => {
    let stopped = false;
    let retryTimer;

    const rejectPending = (error) => {
      for (const pending of pendingRef.current.values()) {
        window.clearTimeout(pending.timeout);
        pending.reject(error);
      }
      pendingRef.current.clear();
    };

    const scheduleReconnect = () => {
      if (!stopped) retryTimer = window.setTimeout(connect, 1200);
    };

    const connect = async () => {
      setConnection("connecting");
      try {
        const ticketResponse = await fetch("/api/auth/ws-ticket", { method: "POST" });
        const ticketPayload = await parseJson(ticketResponse);
        if (!ticketResponse.ok || !ticketPayload.ticket) throw new Error(ticketPayload.detail || "無法取得即時連線票證。");
        if (stopped) return;

        const socket = new WebSocket(socketUrl(ticketPayload.ticket));
        socketRef.current = socket;
        socket.onopen = () => setConnection("connected");
        socket.onmessage = (event) => {
          let message;
          try {
            message = JSON.parse(event.data);
          } catch {
            return;
          }
          if (message.type === "snapshot") {
            setSnapshot(message.payload);
            return;
          }
          if (message.type === "command_result") {
            const pending = pendingRef.current.get(message.id);
            if (!pending) return;
            pendingRef.current.delete(message.id);
            window.clearTimeout(pending.timeout);
            if (message.ok) pending.resolve(message.payload);
            else pending.reject(new Error(message.detail || "操作失敗。"));
          }
        };
        socket.onclose = () => {
          if (socketRef.current === socket) socketRef.current = null;
          rejectPending(new Error("即時連線已中斷。"));
          if (!stopped) {
            setConnection("reconnecting");
            scheduleReconnect();
          }
        };
      } catch {
        if (!stopped) {
          setConnection("reconnecting");
          scheduleReconnect();
        }
      }
    };

    void connect();
    return () => {
      stopped = true;
      window.clearTimeout(retryTimer);
      rejectPending(new Error("即時連線已關閉。"));
      socketRef.current?.close();
    };
  }, []);

  const command = useCallback((action, payload = {}) => new Promise((resolve, reject) => {
    const socket = socketRef.current;
    if (!socket || socket.readyState !== WebSocket.OPEN) {
      reject(new Error("即時連線尚未就緒。"));
      return;
    }
    counterRef.current += 1;
    const id = `cmd_${Date.now()}_${counterRef.current}`;
    const timeout = window.setTimeout(() => {
      pendingRef.current.delete(id);
      reject(new Error("操作逾時。"));
    }, 20000);
    pendingRef.current.set(id, { resolve, reject, timeout });
    socket.send(JSON.stringify({ type: "command", id, action, payload }));
  }), []);

  return { snapshot, connection, command };
}

export default function Dashboard({ actor }) {
  const { snapshot, connection, command } = usePhytoSocket();
  const [toast, setToast] = useState(null);
  const [busyAction, setBusyAction] = useState("");
  const [schedule, setSchedule] = useState(INITIAL_SCHEDULE);
  const [rotation, setRotation] = useState(INITIAL_ROTATION);
  const [moveAngle, setMoveAngle] = useState("0");
  const [sessions, setSessions] = useState([]);
  const [sessionsLoading, setSessionsLoading] = useState(false);
  const [openSettingsGroup, setOpenSettingsGroup] = useState(null);

  const showToast = useCallback((message, tone = "info") => setToast({ id: Date.now(), message, tone }), []);
  const dismissToast = useCallback(() => setToast(null), []);

  const loadSessions = useCallback(async () => {
    setSessionsLoading(true);
    try {
      const response = await fetch("/api/sessions", { cache: "no-store" });
      const payload = await parseJson(response);
      if (!response.ok) throw new Error(payload.detail || "讀取工作階段失敗。");
      setSessions(Array.isArray(payload) ? payload : []);
    } catch (error) {
      showToast(messageFrom(error, "讀取工作階段失敗。"), "error");
    } finally {
      setSessionsLoading(false);
    }
  }, [showToast]);

  useEffect(() => {
    void loadSessions();
  }, [loadSessions]);

  useEffect(() => {
    let active = true;
    async function loadScheduleDefaults() {
      try {
        const response = await fetch("/api/settings/experiment", { cache: "no-store" });
        const payload = await parseJson(response);
        if (!response.ok || !payload.experiment || !active) return;
        const experiment = payload.experiment;
        setSchedule({
          capture_interval_seconds: String(experiment.capture_interval_seconds ?? INITIAL_SCHEDULE.capture_interval_seconds),
          duration_minutes: String(experiment.duration_minutes ?? INITIAL_SCHEDULE.duration_minutes),
          rotation_start_deg: String(experiment.rotation_start_deg ?? INITIAL_SCHEDULE.rotation_start_deg),
          rotation_end_deg: String(experiment.rotation_end_deg ?? INITIAL_SCHEDULE.rotation_end_deg),
          rotation_step_deg: String(experiment.rotation_step_deg ?? INITIAL_SCHEDULE.rotation_step_deg),
        });
        setRotation((previous) => ({
          ...previous,
          start_deg: String(experiment.rotation_start_deg ?? previous.start_deg),
          end_deg: String(experiment.rotation_end_deg ?? previous.end_deg),
          step_deg: String(experiment.rotation_step_deg ?? previous.step_deg),
        }));
      } catch {
        // The live controls remain usable with their safe defaults.
      }
    }
    void loadScheduleDefaults();
    return () => { active = false; };
  }, []);

  const runAction = useCallback(async (action, payload = {}, successMessage) => {
    setBusyAction(action);
    try {
      const result = await command(action, payload);
      if (successMessage) showToast(successMessage, "success");
      return result;
    } catch (error) {
      showToast(messageFrom(error, "操作失敗。"), "error");
      return null;
    } finally {
      setBusyAction("");
    }
  }, [command, showToast]);

  async function handleScheduleSubmit(event) {
    event.preventDefault();
    const result = await runAction("experiment.start", numberPayload(schedule), "實驗已開始。");
    if (result) void loadSessions();
  }

  async function handleRotationSubmit(event) {
    event.preventDefault();
    await runAction("capture.rotation_cycle", numberPayload(rotation), "旋轉擷取循環已執行。");
  }

  async function handleMoveSubmit(event) {
    event.preventDefault();
    await runAction("motor.move", { angle_deg: Number(moveAngle) }, "馬達移動命令已送出。");
  }

  async function logout() {
    await fetch("/api/auth/logout", { method: "POST" });
    window.location.assign("/");
  }

  function toggleSettings(group) {
    setOpenSettingsGroup((current) => (current === group ? null : group));
  }

  const isConnected = connection === "connected";
  const system = snapshot?.system || {};
  const motor = snapshot?.motor || {};
  const experiment = snapshot?.experiment || {};
  const cameras = snapshot?.cameras || [];
  const cameraById = new Map(cameras.map((camera) => [camera.camera_id, camera]));

  return (
    <main className="min-h-screen bg-[#06100c] px-5 pb-8 max-sm:px-3">
      <div>
        <aside className="fixed inset-x-0 top-0 z-40 grid min-h-[4.25rem] grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] items-center gap-4 border-b border-white/10 bg-[#07110d]/80 px-5 py-3 shadow-[0_14px_42px_rgba(0,0,0,0.14)] backdrop-blur-2xl max-[980px]:grid-cols-[minmax(0,1fr)_auto] max-[980px]:gap-2 max-[980px]:px-3 max-[980px]:py-2">
          <div className="grid min-w-0 grid-cols-[2.25rem_minmax(0,1fr)] items-center gap-3">
            <span className="relative grid size-9 place-items-center rounded-2xl border border-emerald-200/20 bg-emerald-300/10 before:size-2 before:rounded-full before:bg-emerald-300" aria-hidden="true" />
            <div className="min-w-0">
              <strong className="block overflow-hidden text-sm font-black tracking-[0.08em] text-white text-ellipsis whitespace-nowrap">PHYTO-AUTOSCOPY</strong>
              <span className="block pt-0.5 text-[11px] font-bold text-white/70">控制台</span>
            </div>
          </div>
          <nav className="flex min-w-0 items-center gap-1 overflow-x-auto rounded-2xl border border-white/10 bg-black/10 p-1 max-[980px]:col-span-full max-[980px]:row-start-2 max-[980px]:w-full" aria-label="主要導覽">
            {[["cameras", "相機預覽"], ["overview", "即時狀態"], ["schedule", "實驗排程"], ["motor", "馬達控制"], ["sessions", "工作階段"]].map(([id, label]) => <NavLink href={`#${id}`} key={id}>{label}</NavLink>)}
          </nav>
          <div className="col-start-3 flex min-w-0 items-center justify-end gap-2 max-[980px]:col-start-2 max-[980px]:row-start-1">
            <span className={`inline-flex min-h-8 items-center rounded-full border px-3 text-xs font-black max-[720px]:hidden ${isConnected ? "border-emerald-200/60 bg-emerald-500/15 text-emerald-200" : "border-amber-200/60 bg-amber-500/15 text-amber-200"}`}>{isConnected ? "即時連線已建立" : "即時連線中"}</span>
            <Button className="min-h-9 px-3 text-xs" variant="danger" disabled={!isConnected || busyAction === "motor.emergency_stop"} onClick={() => void runAction("motor.emergency_stop", {}, "已送出緊急停止命令。")}>緊急停止</Button>
            <Button className="min-h-9 px-2 text-xs" variant="ghost" onClick={() => void logout()}>登出 {actor}</Button>
          </div>
        </aside>

        <div className="mx-auto grid w-full max-w-[112.5rem] gap-4 pt-[5.6rem] min-[981px]:grid-cols-[minmax(0,1fr)_minmax(18.75rem,22.5rem)] max-[980px]:pt-[8.8rem]">
          <CamerasSection cameraMeta={CAMERA_META} cameraById={cameraById} isConnected={isConnected} busyAction={busyAction} open={openSettingsGroup === "cameras"} onToggle={() => toggleSettings("cameras")} onRunAction={runAction} onNotify={showToast} />
          <aside className="grid min-w-0 gap-4 min-[981px]:col-start-2 min-[981px]:row-start-2 min-[981px]:row-span-3 min-[981px]:sticky min-[981px]:top-[5.65rem] min-[981px]:self-start" aria-label="狀態列">
            <StatusSection cameraMeta={CAMERA_META} cameraById={cameraById} connection={connection} experiment={experiment} system={system} />
            <RecentMessagesSection errors={system.recent_errors} />
          </aside>
          <ExperimentSection isConnected={isConnected} busyAction={busyAction} open={openSettingsGroup === "experiment"} onToggle={() => toggleSettings("experiment")} onNotify={showToast} onRunAction={runAction} schedule={schedule} setSchedule={setSchedule} rotation={rotation} setRotation={setRotation} onScheduleSubmit={handleScheduleSubmit} onRotationSubmit={handleRotationSubmit} />
          <MotorSection motor={motor} isConnected={isConnected} busyAction={busyAction} open={openSettingsGroup === "motor"} onToggle={() => toggleSettings("motor")} onNotify={showToast} onRunAction={runAction} moveAngle={moveAngle} setMoveAngle={setMoveAngle} onMoveSubmit={handleMoveSubmit} />
          <SessionsSection sessions={sessions} loading={sessionsLoading} open={openSettingsGroup === "logging"} onToggle={() => toggleSettings("logging")} onNotify={showToast} onLoad={loadSessions} />
        </div>
      </div>
      <ToastViewport key={toast?.id ?? "empty"} toast={toast} onClose={dismissToast} />
    </main>
  );
}

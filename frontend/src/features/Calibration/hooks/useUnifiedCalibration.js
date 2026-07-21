"use client";

import {
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";

import {
  abortRequest,
  messageFromError,
  UnknownMutationOutcomeError,
} from "@/lib/httpUtils";
import usePhytoSocket from "@/hooks/usePhytoSocket";

import {
  loadUnifiedCalibrationWorkspace,
  requestUnifiedCalibration,
} from "../lib/unifiedCalibrationApiUtils";

const CATALOG_REFRESH_INTERVAL_MS = 30_000;
const FINISHED_INTRINSIC_RUN_STATUSES = new Set([
  "applied",
  "cancelled",
]);

function currentIntrinsicRun(value) {
  return Array.isArray(value)
    ? value.find((run) => !FINISHED_INTRINSIC_RUN_STATUSES.has(run.status)) || null
    : null;
}

export default function useUnifiedCalibration({
  polling = false,
}) {
  const {
    snapshot,
    connection,
    socketError,
    resetSocketError,
  } = usePhytoSocket();
  const [status, setStatus] = useState(null);
  const [boards, setBoards] = useState([]);
  const [runs, setRuns] = useState({});
  const [loading, setLoading] = useState(false);
  const [pendingAction, setPendingAction] = useState("");
  const [error, setError] = useState("");
  const [requiresRefresh, setRequiresRefresh] = useState(false);
  const [ownsLock, setOwnsLock] = useState(false);
  const mountedRef = useRef(false);
  const loadControllerRef = useRef(null);
  const actionControllersRef = useRef(new Map());
  const stopControllersRef = useRef(new Map());

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      abortRequest(loadControllerRef.current);
      for (const controller of actionControllersRef.current.values()) {
        abortRequest(controller);
      }
      actionControllersRef.current.clear();
      for (const controller of stopControllersRef.current.values()) {
        abortRequest(controller);
      }
      stopControllersRef.current.clear();
    };
  }, []);

  const load = useCallback(async ({ quiet = false } = {}) => {
    if (loadControllerRef.current) return false;

    const controller = new AbortController();
    loadControllerRef.current = controller;
    if (!quiet) setLoading(true);

    try {
      const [
        nextStatus,
        nextBoards,
        topRuns,
        sideRuns,
        rotatingRuns,
      ] = await loadUnifiedCalibrationWorkspace(controller.signal);
      if (!mountedRef.current || controller.signal.aborted) return false;
      setStatus(nextStatus);
      setOwnsLock(Boolean(nextStatus?.lock_owned_by_requester));
      setBoards(Array.isArray(nextBoards) ? nextBoards : []);
      setRuns({
        top: currentIntrinsicRun(topRuns),
        side: currentIntrinsicRun(sideRuns),
        rotating: currentIntrinsicRun(rotatingRuns),
      });
      setError("");
      setRequiresRefresh(false);
      return true;
    } catch (loadError) {
      if (loadError?.name === "AbortError") return false;
      if (mountedRef.current && !quiet) {
        setError(messageFromError(
          loadError,
          "讀取相機校正資料失敗。",
        ));
      }
      return false;
    } finally {
      if (loadControllerRef.current === controller) {
        loadControllerRef.current = null;
        if (mountedRef.current && !quiet) setLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    const realtimeStatus = snapshot?.calibration;
    if (
      !realtimeStatus
      || typeof realtimeStatus !== "object"
      || Array.isArray(realtimeStatus)
    ) {
      return;
    }

    setStatus(realtimeStatus);
    setOwnsLock(Boolean(realtimeStatus.lock_owned_by_requester));
  }, [snapshot]);

  useEffect(() => {
    if (!polling) return undefined;
    const intervalId = window.setInterval(() => {
      if (document.visibilityState === "visible") {
        void load({ quiet: true });
      }
    }, CATALOG_REFRESH_INTERVAL_MS);
    return () => window.clearInterval(intervalId);
  }, [
    load,
    polling,
  ]);

  useEffect(() => {
    if (!ownsLock) return undefined;

    const releaseLock = () => {
      void fetch("/api/calibration/lock", {
        method: "DELETE",
        keepalive: true,
      }).catch(() => undefined);
    };

    const confirmNavigation = (event) => {
      const anchor = event.target.closest?.("a[href]");
      if (!anchor || anchor.target === "_blank") return;
      if (window.confirm("校正操作尚未結束，離開後將停止自動擷取並釋放校正鎖。確定離開嗎？")) {
        releaseLock();
        return;
      }
      event.preventDefault();
      event.stopPropagation();
    };

    const confirmUnload = (event) => {
      event.preventDefault();
      event.returnValue = "";
    };

    const refreshIntervalId = window.setInterval(() => {
      void requestUnifiedCalibration(
        "/api/calibration/lock/refresh",
        {
          method: "POST",
          timeoutMs: 20_000,
        },
      ).catch((refreshError) => {
        if (!mountedRef.current || refreshError?.name === "AbortError") return;
        setError(messageFromError(
          refreshError,
          "相機校正鎖續期失敗，請重新整理確認校正鎖狀態。",
        ));
        void load({ quiet: true });
      });
    }, 10 * 60 * 1000);

    document.addEventListener("click", confirmNavigation, true);
    window.addEventListener("beforeunload", confirmUnload);
    window.addEventListener("pagehide", releaseLock);
    return () => {
      window.clearInterval(refreshIntervalId);
      document.removeEventListener("click", confirmNavigation, true);
      window.removeEventListener("beforeunload", confirmUnload);
      window.removeEventListener("pagehide", releaseLock);
      releaseLock();
    };
  }, [
    load,
    ownsLock,
  ]);

  const mutate = useCallback(async (
    action,
    path,
    {
      body,
      method = "POST",
      refresh = true,
      successMessage,
      timeoutMs = 60_000,
    } = {},
  ) => {
    if (actionControllersRef.current.has(action) || requiresRefresh) return null;

    if (action.startsWith("intrinsic.") && !action.startsWith("intrinsic.capture.")) {
      const cameraId = action.split(".").at(-1);
      const captureAction = `intrinsic.capture.${cameraId}`;
      const captureController = actionControllersRef.current.get(captureAction);
      if (captureController) {
        abortRequest(captureController);
        actionControllersRef.current.delete(captureAction);
      }
    }

    const controller = new AbortController();
    actionControllersRef.current.set(action, controller);
    if (!action.startsWith("intrinsic.capture.")) {
      setPendingAction(action);
    }
    setError("");

    try {
      const result = await requestUnifiedCalibration(path, {
        body,
        method,
        signal: controller.signal,
        timeoutMs,
      });
      if (!mountedRef.current || controller.signal.aborted) return null;
      setRequiresRefresh(false);
      if (refresh) {
        await load({ quiet: true });
      }
      return {
        result,
        successMessage,
      };
    } catch (mutationError) {
      if (mutationError?.name === "AbortError") return null;
      if (mountedRef.current) {
        const unknown = mutationError instanceof UnknownMutationOutcomeError;
        setRequiresRefresh(unknown);
        setError(messageFromError(
          mutationError,
          "相機校正操作失敗。",
        ));
      }
      return null;
    } finally {
      if (actionControllersRef.current.get(action) === controller) {
        actionControllersRef.current.delete(action);
        if (mountedRef.current && !action.startsWith("intrinsic.capture.")) {
          const nextPendingAction = [...actionControllersRef.current.keys()].find(
            (pending) => !pending.startsWith("intrinsic.capture."),
          ) || "";
          setPendingAction(nextPendingAction);
        }
      }
    }
  }, [
    load,
    requiresRefresh,
  ]);

  const acquireLock = useCallback(async (
    mode,
    details = {},
  ) => {
    const outcome = await mutate(
      "lock.acquire",
      "/api/calibration/lock",
      {
        body: {
          mode,
          ...details,
        },
        successMessage: "已進入相機校正模式。",
      },
    );
    if (outcome && mountedRef.current) setOwnsLock(true);
    return outcome;
  }, [mutate]);

  const releaseLock = useCallback(async () => {
    const outcome = await mutate(
      "lock.release",
      "/api/calibration/lock",
      {
        method: "DELETE",
        successMessage: "已結束相機校正模式。",
      },
    );
    if (outcome && mountedRef.current) setOwnsLock(false);
    return outcome;
  }, [mutate]);

  const stopIntrinsicCalibration = useCallback(async (
    cameraId,
    runId,
  ) => {
    const action = `intrinsic.stop.${cameraId}`;

    for (const [pending, controller] of actionControllersRef.current.entries()) {
      if (!pending.startsWith("intrinsic.")) continue;
      abortRequest(controller, "停止校正命令已優先執行。");
      actionControllersRef.current.delete(pending);
    }

    const previousStopController = stopControllersRef.current.get(action);
    if (previousStopController) {
      abortRequest(previousStopController, "已重新送出停止校正命令。");
    }

    const controller = new AbortController();
    stopControllersRef.current.set(action, controller);
    setPendingAction(action);
    setError("");

    try {
      const result = await requestUnifiedCalibration(
        `/api/calibration/intrinsics/${cameraId}/runs/${encodeURIComponent(runId)}`,
        {
          method: "DELETE",
          signal: controller.signal,
          timeoutMs: 10_000,
        },
      );
      if (!mountedRef.current || controller.signal.aborted) return null;

      setRuns((current) => {
        const next = {
          ...current,
        };
        delete next[cameraId];
        return next;
      });
      setOwnsLock(false);
      setRequiresRefresh(false);
      void load({ quiet: true });

      return {
        result,
        successMessage: "內參校正已停止。",
      };
    } catch (stopError) {
      if (stopError?.name === "AbortError") return null;
      if (mountedRef.current) {
        setError(messageFromError(
          stopError,
          "停止相機校正失敗，請再次按下停止校正。",
        ));
      }
      return null;
    } finally {
      if (stopControllersRef.current.get(action) === controller) {
        stopControllersRef.current.delete(action);
        if (mountedRef.current) {
          const nextStopAction = stopControllersRef.current
            .keys()
            .next()
            .value;
          const nextRegularAction = actionControllersRef.current
            .keys()
            .next()
            .value;
          setPendingAction(nextStopAction || nextRegularAction || "");
        }
      }
    }
  }, [load]);

  const rememberRun = useCallback((cameraId, run) => {
    setRuns((current) => {
      if (!run?.run_id) {
        const next = {
          ...current,
        };
        delete next[cameraId];
        return next;
      }
      return {
        ...current,
        [cameraId]: run,
      };
    });
  }, []);

  const clearError = useCallback(() => {
    setError("");
  }, []);

  return {
    status,
    boards,
    runs,
    loading,
    pendingAction,
    error,
    requiresRefresh,
    ownsLock,
    systemActive: Boolean(snapshot?.system?.active),
    load,
    mutate,
    acquireLock,
    releaseLock,
    stopIntrinsicCalibration,
    rememberRun,
    clearError,
    connection,
    socketError,
    resetSocketError,
  };
}

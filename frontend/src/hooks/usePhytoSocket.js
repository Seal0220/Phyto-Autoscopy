"use client";

import {
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";

import {
  parseJsonResponse,
  responseErrorMessage,
} from "@/lib/httpUtils";

const DEFAULT_COMMAND_TIMEOUT_MS = 20000;
const RECONNECT_DELAYS_MS = [1200, 2500, 5000, 10000, 20000, 30000];
const STABLE_CONNECTION_MS = 30000;
const REPEATED_ERROR_DELAY_MS = 10000;

function socketUrl(ticket) {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${protocol}//${window.location.host}/ws/status?ticket=${encodeURIComponent(ticket)}`;
}

function safeSocketDetail(
  value,
  fallback,
) {
  if (typeof value !== "string") return fallback;

  const detail = value.trim();

  if (
    !detail
    || detail.length > 500
    || /[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/.test(detail)
  ) {
    return fallback;
  }

  return detail;
}

function retryAfterMilliseconds(value) {
  const seconds = Number(value);

  if (!Number.isFinite(seconds) || seconds <= 0) return null;
  return Math.min(Math.ceil(seconds * 1000), 60000);
}

export default function usePhytoSocket() {
  const [snapshot, setSnapshot] = useState(null);
  const [connection, setConnection] = useState("connecting");
  const [socketError, setSocketError] = useState(null);
  const [authExpired, setAuthExpired] = useState(false);
  const socketRef = useRef(null);
  const pendingRef = useRef(new Map());
  const counterRef = useRef(0);
  const errorCounterRef = useRef(0);
  const lastReportedErrorRef = useRef(null);

  const reportSocketError = useCallback((message) => {
    const now = Date.now();
    const previous = lastReportedErrorRef.current;

    if (
      previous?.message === message
      && now - previous.reportedAt < REPEATED_ERROR_DELAY_MS
    ) {
      return;
    }

    errorCounterRef.current += 1;
    lastReportedErrorRef.current = {
      message,
      reportedAt: now,
    };
    setSocketError({
      id: `socket-error-${now}-${errorCounterRef.current}`,
      message,
    });
  }, []);

  const resetSocketError = useCallback(() => {
    lastReportedErrorRef.current = null;
    setSocketError(null);
  }, []);

  useEffect(() => {
    let stopped = false;
    let retryTimer;
    let ticketController;
    let reconnectAttempt = 0;

    const rejectPending = (error) => {
      for (const pending of pendingRef.current.values()) {
        window.clearTimeout(pending.timeout);
        pending.reject(error);
      }
      pendingRef.current.clear();
    };

    const scheduleReconnect = (delayOverride = null) => {
      window.clearTimeout(retryTimer);

      if (!stopped) {
        const retryDelay = delayOverride ?? RECONNECT_DELAYS_MS[
          Math.min(
            reconnectAttempt,
            RECONNECT_DELAYS_MS.length - 1,
          )
        ];
        reconnectAttempt += 1;
        retryTimer = window.setTimeout(connect, retryDelay);
      }
    };

    const connect = async () => {
      if (stopped) return;

      setConnection("connecting");
      ticketController?.abort();
      ticketController = new AbortController();

      try {
        const ticketResponse = await fetch("/api/auth/ws-ticket", {
          method: "POST",
          signal: ticketController.signal,
        });
        const ticketPayload = await parseJsonResponse(ticketResponse);

        if ([401, 403].includes(ticketResponse.status)) {
          if (!stopped) {
            setConnection("unauthorized");
            setAuthExpired(true);
            reportSocketError("登入狀態已失效，請重新登入。");
          }

          return;
        }

        if (!ticketResponse.ok || typeof ticketPayload.ticket !== "string") {
          const ticketError = new Error(responseErrorMessage(
            ticketPayload,
            "無法取得即時連線票證。",
          ));

          if (ticketResponse.status === 429) {
            ticketError.retryAfterMs = retryAfterMilliseconds(
              ticketResponse.headers.get("Retry-After"),
            );
          }

          throw ticketError;
        }

        if (stopped) return;

        const socket = new WebSocket(socketUrl(ticketPayload.ticket));
        let socketFailureReported = false;
        let socketOpenedAt = 0;
        socketRef.current = socket;
        socket.onopen = () => {
          if (stopped || socketRef.current !== socket) {
            try {
              socket.close();
            } catch {
              // The socket is already unusable, so no further recovery is required here.
            }

            return;
          }

          lastReportedErrorRef.current = null;
          setSocketError(null);
          setAuthExpired(false);
          setConnection("connected");
          socketOpenedAt = Date.now();
        };
        socket.onmessage = (event) => {
          if (stopped || socketRef.current !== socket) return;

          let message;

          try {
            message = JSON.parse(event.data);
          } catch {
            reportSocketError("收到無法解析的即時訊息，已忽略該訊息並維持連線。");
            return;
          }

          if (!message || typeof message !== "object" || Array.isArray(message)) {
            reportSocketError("收到格式無效的即時訊息，已忽略該訊息並維持連線。");
            return;
          }

          if (message.type === "snapshot") {
            if (!message.payload || typeof message.payload !== "object") {
              reportSocketError("收到格式無效的系統狀態，已保留上一筆狀態並維持連線。");
              return;
            }

            setSnapshot(message.payload);
            return;
          }

          if (message.type === "command_result") {
            if (typeof message.id !== "string") {
              reportSocketError("收到缺少識別碼的操作結果，已忽略該訊息並維持連線。");
              return;
            }

            const pending = pendingRef.current.get(message.id);
            if (!pending) return;

            pendingRef.current.delete(message.id);
            window.clearTimeout(pending.timeout);

            if (typeof message.ok !== "boolean") {
              pending.reject(new Error("伺服器回傳的操作結果格式無效，請重試。"));
              reportSocketError("收到格式無效的操作結果，請重新執行該操作。");
              return;
            }

            if (message.ok) {
              pending.resolve(message.payload);
            } else {
              const commandError = new Error(safeSocketDetail(
                message.detail,
                "操作失敗。",
              ));

              if (typeof message.code === "string" && message.code.trim()) {
                commandError.code = message.code.trim();
              }

              pending.reject(commandError);
            }

            return;
          }

          if (message.type === "error") {
            reportSocketError(safeSocketDetail(
              message.detail,
              "即時連線回報未提供內容的錯誤。",
            ));
            return;
          }

          reportSocketError("收到不支援的即時訊息類型，已忽略該訊息並維持連線。");
        };
        socket.onerror = () => {
          if (stopped || socketRef.current !== socket) return;

          socketFailureReported = true;
          reportSocketError("即時連線發生錯誤，系統正在自動重新連線。");

          try {
            socket.close();
          } catch {
            if (socketRef.current === socket) {
              socketRef.current = null;
            }

            rejectPending(new Error("即時連線已中斷。"));
            setConnection("reconnecting");
            scheduleReconnect();
          }
        };
        socket.onclose = () => {
          if (socketRef.current !== socket) return;

          socketRef.current = null;
          rejectPending(new Error("即時連線已中斷。"));

          if (!stopped) {
            if (
              socketOpenedAt
              && Date.now() - socketOpenedAt >= STABLE_CONNECTION_MS
            ) {
              reconnectAttempt = 0;
            }

            if (!socketFailureReported) {
              reportSocketError("即時連線已中斷，系統正在自動重新連線。");
            }

            setConnection("reconnecting");
            scheduleReconnect();
          }
        };
      } catch (error) {
        if (error?.name === "AbortError") return;

        if (!stopped) {
          const message = error instanceof Error
            && error.message
            && !(error instanceof TypeError)
            ? `${error.message} 系統將自動重試。`
            : "無法建立即時連線，系統將自動重試。";

          reportSocketError(message);
          setConnection("reconnecting");
          scheduleReconnect(error?.retryAfterMs);
        }
      }
    };

    void connect();
    return () => {
      stopped = true;
      window.clearTimeout(retryTimer);
      ticketController?.abort();
      rejectPending(new Error("即時連線已關閉。"));
      const socket = socketRef.current;

      if (socket) {
        socketRef.current = null;
        socket.onopen = null;
        socket.onmessage = null;
        socket.onerror = null;
        socket.onclose = null;

        try {
          socket.close();
        } catch {
          // Cleanup is complete even if the browser rejects a redundant close.
        }
      }
    };
  }, [reportSocketError]);

  const command = useCallback((
    action,
    payload = {},
  ) => new Promise((
    resolve,
    reject,
  ) => {
    const socket = socketRef.current;

    if (!socket || socket.readyState !== WebSocket.OPEN) {
      reject(new Error("即時連線尚未就緒。"));
      return;
    }

    counterRef.current += 1;
    const id = `cmd_${Date.now()}_${counterRef.current}`;
    const timeout = window.setTimeout(() => {
      pendingRef.current.delete(id);
      reject(new Error("操作逾時，請重試。"));
    }, DEFAULT_COMMAND_TIMEOUT_MS);

    pendingRef.current.set(id, {
      resolve,
      reject,
      timeout,
    });

    try {
      socket.send(JSON.stringify({
        type: "command",
        id,
        action,
        payload,
      }));
    } catch {
      pendingRef.current.delete(id);
      window.clearTimeout(timeout);
      reject(new Error("操作命令傳送失敗，請稍後重試。"));

      try {
        socket.close();
      } catch {
        // onclose/onerror will handle reconnecting when the socket can still emit events.
      }
    }
  }), []);

  return {
    snapshot,
    connection,
    socketError,
    authExpired,
    resetSocketError,
    command,
  };
}

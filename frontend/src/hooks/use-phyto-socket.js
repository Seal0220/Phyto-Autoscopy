"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { parseJsonResponse } from "@/lib/http";

function socketUrl(ticket) {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${protocol}//${window.location.host}/ws/status?ticket=${encodeURIComponent(ticket)}`;
}

export default function usePhytoSocket() {
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
        const ticketPayload = await parseJsonResponse(ticketResponse);
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

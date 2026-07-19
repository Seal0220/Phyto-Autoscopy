"use client";

import { useCallback, useRef, useState } from "react";

import { normalizeSystemError } from "../lib/notificationUtils";

export default function useNotifications() {
  const [toast, setToast] = useState(null);
  const [notifications, setNotifications] = useState([]);
  const counterRef = useRef(0);
  const seenSystemMessagesRef = useRef(new Set());
  const lastNotificationRef = useRef(null);

  const showNotification = useCallback((message, tone = "info") => {
    const normalizedMessage = typeof message === "string"
      ? message.trim()
      : "";
    if (!normalizedMessage) return;

    const now = Date.now();
    const previous = lastNotificationRef.current;
    if (
      previous?.message === normalizedMessage
      && previous.tone === tone
      && now - previous.createdAt < 1_000
    ) {
      return;
    }

    counterRef.current += 1;
    const notification = {
      id: `${now}-${counterRef.current}`,
      message: normalizedMessage,
      tone,
      createdAt: now,
    };
    lastNotificationRef.current = notification;
    setToast(notification);
    setNotifications((previous) => [notification, ...previous].slice(0, 50));
  }, []);

  const dismissNotification = useCallback(() => setToast(null), []);

  const clearNotifications = useCallback(() => {
    seenSystemMessagesRef.current.clear();
    lastNotificationRef.current = null;
    setToast(null);
    setNotifications([]);
  }, []);

  const syncRecentErrors = useCallback((recentErrors) => {
    if (!Array.isArray(recentErrors)) return;
    for (const error of recentErrors) {
      const message = normalizeSystemError(error);
      if (seenSystemMessagesRef.current.has(message)) continue;
      seenSystemMessagesRef.current.add(message);
      showNotification(message, "error");
    }
  }, [showNotification]);

  return {
    toast,
    notifications,
    showNotification,
    dismissNotification,
    clearNotifications,
    syncRecentErrors,
  };
}

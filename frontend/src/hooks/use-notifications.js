"use client";

import { useCallback, useEffect, useRef, useState } from "react";

export default function useNotifications(recentErrors) {
  const [toast, setToast] = useState(null);
  const [notifications, setNotifications] = useState([]);
  const counterRef = useRef(0);
  const seenSystemMessagesRef = useRef(new Set());

  const showNotification = useCallback((message, tone = "info") => {
    counterRef.current += 1;
    const notification = {
      id: `${Date.now()}-${counterRef.current}`,
      message,
      tone,
      createdAt: Date.now(),
    };
    setToast(notification);
    setNotifications((previous) => [notification, ...previous].slice(0, 50));
  }, []);

  const dismissNotification = useCallback(() => setToast(null), []);

  useEffect(() => {
    if (!Array.isArray(recentErrors)) return;
    for (const error of recentErrors) {
      const message = String(error);
      if (seenSystemMessagesRef.current.has(message)) continue;
      seenSystemMessagesRef.current.add(message);
      showNotification(message, "error");
    }
  }, [recentErrors, showNotification]);

  return {
    toast,
    notifications,
    showNotification,
    dismissNotification,
  };
}

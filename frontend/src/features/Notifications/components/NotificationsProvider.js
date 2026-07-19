"use client";

import {
  useCallback,
  useMemo,
  useRef,
  useState,
} from "react";

import {
  messageFromError,
  parseJsonResponse,
  responseErrorMessage,
} from "@/lib/httpUtils";

import Notifications from "../Notifications";
import NotificationsContext from "../NotificationsContext";
import useNotifications from "../hooks/useNotifications";

export default function NotificationsProvider({ children }) {
  const {
    toast,
    notifications,
    showNotification,
    dismissNotification,
    clearNotifications,
    syncRecentErrors,
  } = useNotifications();
  const [clearing, setClearing] = useState(false);
  const clearingRef = useRef(false);

  const clearAllNotifications = useCallback(async () => {
    if (clearingRef.current) return false;

    clearingRef.current = true;
    setClearing(true);

    try {
      const response = await fetch("/api/system/errors/reset", {
        method: "POST",
      });
      const payload = await parseJsonResponse(response);

      if (!response.ok) {
        throw new Error(responseErrorMessage(
          payload,
          "清除通知失敗。",
        ));
      }

      clearNotifications();
      return true;
    } catch (error) {
      showNotification(
        messageFromError(error, "清除通知失敗。"),
        "error",
      );
      return false;
    } finally {
      clearingRef.current = false;
      setClearing(false);
    }
  }, [
    clearNotifications,
    showNotification,
  ]);

  const value = useMemo(() => ({
    showNotification,
    dismissNotification,
    clearNotifications,
    syncRecentErrors,
  }), [
    clearNotifications,
    dismissNotification,
    showNotification,
    syncRecentErrors,
  ]);

  return (
    <NotificationsContext.Provider value={value}>
      {children}
      <Notifications
        toast={toast}
        notifications={notifications}
        clearing={clearing}
        clearDisabled={clearing}
        onClear={() => void clearAllNotifications()}
        onClose={dismissNotification}
      />
    </NotificationsContext.Provider>
  );
}

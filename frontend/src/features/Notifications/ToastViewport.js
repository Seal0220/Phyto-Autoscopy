"use client";

import { useEffect, useState } from "react";

import NotificationHistory from "@/components/notifications/notification-history";
import NotificationToast from "@/components/notifications/notification-toast";
import NotificationTrigger from "@/components/notifications/notification-trigger";

export default function ToastViewport({ toast, notifications = [], onClose }) {
  const [historyOpen, setHistoryOpen] = useState(false);

  useEffect(() => {
    if (!toast) return undefined;
    const timer = window.setTimeout(onClose, 4500);
    return () => window.clearTimeout(timer);
  }, [toast, onClose]);

  return (
    <div className="fixed right-5 bottom-5 z-60 flex w-[min(25rem,calc(100vw-2.5rem))] flex-col items-end gap-2 max-sm:right-3 max-sm:bottom-3 max-sm:w-[calc(100vw-1.5rem)]">
      <NotificationToast toast={toast} onClose={onClose} />
      {historyOpen ? <NotificationHistory notifications={notifications} onClose={() => setHistoryOpen(false)} /> : null}
      <NotificationTrigger open={historyOpen} count={notifications.length} onClick={() => setHistoryOpen((current) => !current)} />
    </div>
  );
}

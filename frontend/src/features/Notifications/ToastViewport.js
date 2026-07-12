"use client";

import { useEffect, useState } from "react";

import History from "@/features/Notifications/components/History";
import Toast from "@/features/Notifications/components/Toast";
import Trigger from "@/features/Notifications/components/Trigger";

export default function ToastViewport({
  toast,
  notifications = [],
  onClose,
}) {
  const [historyOpen, setHistoryOpen] = useState(false);

  useEffect(() => {
    if (!toast) return undefined;
    const timer = window.setTimeout(onClose, 4500);
    return () => window.clearTimeout(timer);
  }, [toast, onClose]);

  return (
    <div className="fixed right-5 bottom-5 z-60 flex w-[min(25rem,calc(100vw-2.5rem))] flex-col items-end gap-2 max-sm:right-3 max-sm:bottom-3 max-sm:w-[calc(100vw-1.5rem)]">
      <Toast
        toast={toast}
        onClose={onClose}
      />
      {historyOpen ? (
        <History
          notifications={notifications}
          onClose={() => setHistoryOpen(false)}
        />
      ) : null}
      <Trigger
        open={historyOpen}
        count={notifications.length}
        onClick={() => setHistoryOpen((current) => !current)}
      />
    </div>
  );
}

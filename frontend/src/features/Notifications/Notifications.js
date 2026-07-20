"use client";

import { useEffect, useState } from "react";
import { createPortal } from "react-dom";

import NotificationsHistory from "@/features/Notifications/components/NotificationsHistory";
import NotificationsToast from "@/features/Notifications/components/NotificationsToast";
import NotificationsTrigger from "@/features/Notifications/components/NotificationsTrigger";
import { NOTIFICATION_FADE_DURATION_MS } from "@/features/Notifications/notificationConfig";

export default function Notifications({
  toast,
  notifications = [],
  clearing = false,
  clearDisabled = false,
  onClear,
  onClose,
}) {
  const [mounted, setMounted] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [renderedToast, setRenderedToast] = useState(toast);
  const [toastOpen, setToastOpen] = useState(Boolean(toast));

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    let frame;
    let removeTimer;

    if (toast) {
      setRenderedToast(toast);
      setToastOpen(false);
      frame = window.requestAnimationFrame(() => setToastOpen(true));
    } else {
      setToastOpen(false);
      removeTimer = window.setTimeout(
        () => setRenderedToast(null),
        NOTIFICATION_FADE_DURATION_MS,
      );
    }

    return () => {
      if (frame) window.cancelAnimationFrame(frame);
      if (removeTimer) window.clearTimeout(removeTimer);
    };
  }, [toast]);

  useEffect(() => {
    if (!toast) return undefined;
    const timer = window.setTimeout(onClose, 4500);
    return () => window.clearTimeout(timer);
  }, [toast, onClose]);

  if (!mounted) return null;

  return createPortal(
    <div className="fixed right-5 bottom-5 z-400 flex w-[min(25rem,calc(100vw-2.5rem))] flex-col items-end gap-2 max-sm:right-3 max-sm:bottom-3 max-sm:w-[calc(100vw-1.5rem)]">
      <NotificationsToast
        toast={renderedToast}
        open={toastOpen}
        onClose={onClose}
      />
      <div className="grid w-full justify-items-end">
        <div
          className={`
            grid w-full transition-[grid-template-rows,margin] duration-400 ease-in-out motion-reduce:transition-none
            ${historyOpen
              ? "mb-2 grid-rows-[1fr]"
              : "pointer-events-none mb-0 grid-rows-[0fr]"
            }
          `}
          aria-hidden={!historyOpen}
          inert={!historyOpen}
        >
          <div className="min-h-0 overflow-hidden">
            <NotificationsHistory
              open={historyOpen}
              notifications={notifications}
              clearing={clearing}
              clearDisabled={clearDisabled}
              onClear={onClear}
              onClose={() => setHistoryOpen(false)}
            />
          </div>
        </div>
        <NotificationsTrigger
          open={historyOpen}
          count={notifications.length}
          onClick={() => setHistoryOpen((current) => !current)}
        />
      </div>
    </div>,
    document.body,
  );
}

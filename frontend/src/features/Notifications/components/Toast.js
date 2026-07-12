import { FiX } from "react-icons/fi";

import { notificationMeta } from "@/components/notifications/notification-meta";

export default function NotificationToast({ toast, onClose }) {
  if (!toast) return null;
  const meta = notificationMeta(toast.tone);
  const Icon = meta.Icon;
  return (
    <div className={`flex w-full items-start gap-3 rounded-xl border border-white/20 border-l-[3px] bg-[#08140f]/95 px-4 py-3 text-slate-100 shadow-2xl backdrop-blur-xl motion-safe:animate-[fade-in_180ms_ease-out] ${meta.border}`} role="status" aria-live="polite">
      <Icon className={`mt-1 size-4 shrink-0 ${meta.icon}`} aria-hidden="true" />
      <p className="min-w-0 flex-1 text-sm leading-6">{toast.message}</p>
      <button className="grid size-7 shrink-0 cursor-pointer place-items-center rounded-md text-neutral-400 transition-colors hover:bg-white/10 hover:text-white focus-visible:outline-2 focus-visible:outline-emerald-300" type="button" aria-label="關閉目前訊息" onClick={onClose}>
        <FiX className="size-4" aria-hidden="true" />
      </button>
    </div>
  );
}

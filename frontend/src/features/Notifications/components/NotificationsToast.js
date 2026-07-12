import { FiX } from "react-icons/fi";

import { notificationMeta } from "@/features/Notifications/lib/notificationUtils";

export default function NotificationsToast({
  toast,
  open,
  onClose,
}) {
  if (!toast) return null;
  const meta = notificationMeta(toast.tone);
  const Icon = meta.Icon;
  return (
    <div
      className={`flex w-full items-start gap-3 rounded-xl border border-white/20 border-l-[3px] bg-[#08140f]/95 px-4 py-3 text-slate-100 shadow-2xl backdrop-blur-xl transition-opacity duration-200 ease-in-out will-change-[opacity] motion-reduce:transition-none ${open ? "opacity-100" : "pointer-events-none opacity-0"} ${meta.border}`}
      role="status"
      aria-live="polite"
    >
      <Icon className={`mt-1 size-4 shrink-0 ${meta.icon}`} aria-hidden="true" />
      <p className="min-w-0 flex-1 text-sm leading-6">{toast.message}</p>
      <button
        className="grid size-7 shrink-0 cursor-pointer place-items-center rounded-md text-neutral-400 transition-[background-color,color] duration-150 motion-reduce:transition-none hover:bg-white/10 hover:text-white focus-visible:outline-2 focus-visible:outline-emerald-300"
        type="button"
        aria-label="關閉目前通知"
        onClick={onClose}
      >
        <FiX className="size-4" aria-hidden="true" />
      </button>
    </div>
  );
}

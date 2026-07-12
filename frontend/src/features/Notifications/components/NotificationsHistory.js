import { FiBell, FiChevronDown } from "react-icons/fi";

import { notificationMeta } from "@/features/Notifications/lib/notificationUtils";
import { formatClockTime } from "@/lib/formatUtils";

export default function NotificationsHistory({
  open,
  notifications,
  onClose,
}) {
  return (
    <section
      className={`grid max-h-[min(32rem,calc(100vh-8rem))] w-full grid-rows-[auto_minmax(0,1fr)] overflow-hidden rounded-2xl border border-white/15 bg-[#08140f]/95 text-slate-100 shadow-2xl backdrop-blur-2xl transition-opacity duration-200 ease-in-out will-change-[opacity] motion-reduce:transition-none ${open ? "opacity-100" : "opacity-0"}`}
      aria-label="歷史通知"
    >
      <header className="flex min-h-13 items-center gap-3 border-b border-white/10 px-4 py-3">
        <FiBell className="size-4 text-emerald-300" aria-hidden="true" />
        <h2 className="m-0 flex-1 text-sm font-black">歷史通知</h2>
        <span className="text-xs font-bold text-neutral-500">最近 {notifications.length} 則</span>
        <button
          className="grid size-7 cursor-pointer place-items-center rounded-md text-neutral-400 transition-[background-color,color] duration-150 motion-reduce:transition-none hover:bg-white/10 hover:text-white focus-visible:outline-2 focus-visible:outline-emerald-300"
          type="button"
          aria-label="收合歷史通知"
          onClick={onClose}
        >
          <FiChevronDown className="size-4" aria-hidden="true" />
        </button>
      </header>
      <div className="overflow-y-auto overscroll-contain">
        {notifications.length ? (
          <ol className="divide-y divide-white/10">
            {notifications.map((notification) => {
              const meta = notificationMeta(notification.tone);
              const Icon = meta.Icon;
              return (
                <li
                  className="grid grid-cols-[auto_minmax(0,1fr)] gap-3 px-4 py-3"
                  key={notification.id}
                >
                  <Icon
                    className={`mt-0.5 size-4 ${meta.icon}`}
                    aria-hidden="true"
                  />
                  <div className="min-w-0">
                    <div className="mb-1 flex items-center justify-between gap-3">
                      <span className="text-[11px] font-black text-neutral-400">{meta.label}</span>
                      <time
                        className="text-[11px] font-semibold text-neutral-600"
                        dateTime={new Date(notification.createdAt).toISOString()}
                      >
                        {formatClockTime(notification.createdAt)}
                      </time>
                    </div>
                    <p className="text-sm leading-5 text-neutral-200">{notification.message}</p>
                  </div>
                </li>
              );
            })}
          </ol>
        ) : (
          <p className="px-4 py-8 text-center text-sm font-semibold text-neutral-500">尚無通知</p>
        )}
      </div>
    </section>
  );
}

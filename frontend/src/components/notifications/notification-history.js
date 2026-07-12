import { FiBell, FiChevronDown } from "react-icons/fi";

import { notificationMeta } from "@/components/notifications/notification-meta";
import { formatClockTime } from "@/lib/format";

export default function NotificationHistory({ notifications, onClose }) {
  return (
    <section className="grid max-h-[min(32rem,calc(100vh-8rem))] w-full grid-rows-[auto_minmax(0,1fr)] overflow-hidden rounded-2xl border border-white/15 bg-[#08140f]/95 text-slate-100 shadow-2xl backdrop-blur-2xl" aria-label="歷史訊息">
      <header className="flex min-h-13 items-center gap-3 border-b border-white/10 px-4 py-3">
        <FiBell className="size-4 text-emerald-300" aria-hidden="true" />
        <h2 className="m-0 flex-1 text-sm font-black">歷史訊息</h2>
        <span className="text-xs font-bold text-neutral-500">最近 {notifications.length} 則</span>
        <button className="grid size-7 cursor-pointer place-items-center rounded-md text-neutral-400 transition-colors hover:bg-white/10 hover:text-white focus-visible:outline-2 focus-visible:outline-emerald-300" type="button" aria-label="收合歷史訊息" onClick={onClose}>
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
                <li className="grid grid-cols-[auto_minmax(0,1fr)] gap-3 px-4 py-3" key={notification.id}>
                  <Icon className={`mt-0.5 size-4 ${meta.icon}`} aria-hidden="true" />
                  <div className="min-w-0">
                    <div className="mb-1 flex items-center justify-between gap-3">
                      <span className="text-[11px] font-black text-neutral-400">{meta.label}</span>
                      <time className="text-[11px] font-semibold text-neutral-600" dateTime={new Date(notification.createdAt).toISOString()}>{formatClockTime(notification.createdAt)}</time>
                    </div>
                    <p className="text-sm leading-5 text-neutral-200">{notification.message}</p>
                  </div>
                </li>
              );
            })}
          </ol>
        ) : (
          <p className="px-4 py-8 text-center text-sm font-semibold text-neutral-500">尚無訊息</p>
        )}
      </div>
    </section>
  );
}

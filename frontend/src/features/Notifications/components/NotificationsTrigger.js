import { FiBell } from "react-icons/fi";

export default function NotificationsTrigger({
  open,
  count,
  onClick,
}) {
  return (
    <button
      className={`inline-flex min-h-11 cursor-pointer items-center gap-2 rounded-xl border px-3.5 text-sm font-black shadow-xl backdrop-blur-xl transition-[background-color,border-color,color] duration-150 motion-reduce:transition-none focus-visible:outline-2 focus-visible:outline-emerald-300 ${
        open
          ? "border-emerald-200/60 bg-emerald-400/20 text-emerald-100"
          : "border-white/15 bg-[#08140f]/90 text-neutral-200 hover:border-emerald-200/45 hover:bg-emerald-400/15 hover:text-emerald-100"
      }`}
      type="button"
      aria-expanded={open}
      aria-label={open ? "收合歷史通知" : "展開歷史通知"}
      onClick={onClick}
    >
      <FiBell className="size-4" aria-hidden="true" />
      <span>通知</span>
      {count ? (
        <span className="grid min-w-5 place-items-center rounded-full bg-white/10 px-1.5 py-0.5 text-[10px] leading-4">
          {Math.min(count, 50)}
        </span>
      ) : null}
    </button>
  );
}

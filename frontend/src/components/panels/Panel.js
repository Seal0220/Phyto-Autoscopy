export const PANEL_CLASS = "relative z-0 min-w-0 overflow-visible rounded-[28px] border border-white/15 bg-white/[0.07] shadow-[0_24px_80px_rgba(0,0,0,0.26),inset_0_1px_0_rgba(255,255,255,0.08)] backdrop-blur-2xl hover:z-100 focus-within:z-100";

const TONE_STYLES = {
  success: "border-emerald-200/75 bg-emerald-500/20 text-emerald-200",
  warning: "border-amber-200/75 bg-amber-500/20 text-amber-200",
  offline: "border-rose-200/75 bg-rose-500/20 text-rose-200",
  neutral: "border-white/15 bg-black/20 text-neutral-200",
};

export function Panel({
  as: Component = "section",
  className,
  ...props
}) {
  return (
    <Component
      className={`${PANEL_CLASS} ${className || ""}`}
      {...props}
    />
  );
}

export function PanelHeader({
  title,
  action,
  muted = false,
}) {
  return (
    <div className="flex min-h-[68px] items-center gap-4 rounded-t-[27px] border-b border-white/15 bg-white/[0.04] px-5 py-4 max-sm:flex-wrap max-sm:px-4">
      <span
        className={`size-2 shrink-0 rounded-full ${muted ? "bg-neutral-500" : "bg-emerald-300"}`}
        aria-hidden="true"
      />
      <div>
        <h2 className="m-0 text-lg font-black tracking-tight text-white">{title}</h2>
      </div>
      <div className="min-w-4 flex-1 border-t border-white/15" />
      {action}
    </div>
  );
}

export function StatusPill({
  children,
  tone = "neutral",
  compact = false,
}) {
  return (
    <span
      className={`inline-flex min-w-0 items-center justify-center rounded-full border text-center font-black before:size-1.5 before:shrink-0 before:rounded-full before:bg-current
        ${compact
          ? "min-h-5 max-w-full gap-1 px-2 py-0.5 text-[10px] leading-tight whitespace-normal break-words"
          : "min-h-7 gap-2 px-3 py-1 text-[11px] tracking-[0.04em] whitespace-nowrap"
        } ${TONE_STYLES[tone] || TONE_STYLES.neutral}`}
    >
      {children}
    </span>
  );
}

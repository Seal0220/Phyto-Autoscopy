export const CONTROL_CLASS = "min-h-11 w-full rounded-xl border border-white/10 bg-black/15 px-3 py-2 text-sm font-semibold text-white outline-none transition hover:border-white/20 focus:border-emerald-300/60 focus:ring-4 focus:ring-emerald-300/10";

export function Input({ className, ...props }) {
  return <input className={`${CONTROL_CLASS} ${className || ""}`} {...props} />;
}

export function Select({ className, children, ...props }) {
  return <select className={`${CONTROL_CLASS} appearance-none ${className || ""}`} {...props}>{children}</select>;
}

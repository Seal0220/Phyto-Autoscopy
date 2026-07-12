const VARIANTS = {
  default: "border-white/15 bg-white/[0.07] text-neutral-200 hover:border-white/25 hover:bg-white/[0.13]",
  primary: "border-emerald-200/35 bg-emerald-400 text-emerald-950 hover:border-emerald-100/70 hover:bg-emerald-300",
  danger: "border-rose-300/80 bg-rose-600 text-white hover:border-rose-100 hover:bg-rose-500",
  ghost: "border-transparent bg-transparent text-neutral-300 hover:bg-white/15 hover:text-white",
  dangerGhost: "border-transparent bg-transparent text-neutral-300 hover:bg-rose-500/15 hover:text-rose-200",
};

export default function Button({
  className,
  variant = "default",
  type = "button",
  ...props
}) {
  return (
    <button
      type={type}
      className={`inline-flex min-h-10 min-w-0 cursor-pointer items-center justify-center rounded-xl border px-4 py-2 text-sm font-extrabold transition-[background-color,border-color,color,opacity] duration-150 focus-visible:outline-2 focus-visible:outline-emerald-300 disabled:cursor-not-allowed disabled:opacity-45 ${VARIANTS[variant]} ${className || ""}`}
      {...props}
    />
  );
}

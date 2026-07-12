export default function NavLink({
  className,
  ...props
}) {
  return (
    <a
      className={`inline-flex min-h-9 shrink-0 items-center justify-center rounded-xl px-3 text-sm font-black text-neutral-400 transition hover:bg-white/10 hover:text-white focus-visible:outline-2 focus-visible:outline-emerald-300 ${className || ""}`}
      {...props}
    />
  );
}

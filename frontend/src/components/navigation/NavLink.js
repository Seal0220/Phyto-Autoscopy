import Link from "next/link";

export default function NavLink({
  children,
  className,
  disabled = false,
  onClick,
  ...props
}) {
  return (
    <Link
      className={`inline-flex min-h-9 shrink-0 items-center justify-center rounded-xl px-3 text-sm font-black text-neutral-400 transition hover:bg-white/10 hover:text-white focus-visible:outline-2 focus-visible:outline-emerald-300 ${className || ""}`}
      {...props}
      aria-disabled={disabled || undefined}
      tabIndex={disabled ? -1 : props.tabIndex}
      onClick={(event) => {
        if (disabled) {
          event.preventDefault();
          return;
        }
        onClick?.(event);
      }}
    >
      {children}
    </Link>
  );
}

export default function InnerPanel({
  as: Component = "div",
  children,
  className,
  mode = "light", // "light" / "dark"
  ...props
}) {
  return (
    <Component
      className={`grid gap-4 rounded-xl border border-white/15 ${mode === "light" ? "bg-white/6" : "bg-black/15"} p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.07)] ${className || ""}`}
      {...props}
    >
      {children}
    </Component>
  );
}

export default function InnerPanel({
  as: Component = "div",
  children,
  className,
  ...props
}) {
  return (
    <Component
      className={`grid gap-4 rounded-[22px] border border-white/10 bg-white/6 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.07)] ${className || ""}`}
      {...props}
    >
      {children}
    </Component>
  );
}

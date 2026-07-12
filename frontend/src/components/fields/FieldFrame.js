import Tooltip from "@/components/Tooltip";

export function FieldFrame({
  label,
  children,
  description,
  className,
}) {
  return (
    <div className={`group relative min-w-0 focus-within:z-90 hover:z-100 ${className || ""}`}>
      <div className="relative min-w-0 pt-1">
        <span className="pointer-events-none absolute -top-0.5 left-3 z-10 text-xs font-black leading-none text-neutral-300">{label}</span>
        {children}
      </div>
      {description ? <Tooltip>{description}</Tooltip> : null}
    </div>
  );
}

import Toggle from "@/components/ui/toggle";
import Tooltip from "@/components/ui/tooltip";

export default function ToggleRow({
  checked,
  label,
  description,
  status,
  disabled = false,
  onClick,
  className,
}) {
  return (
    <button
      type="button"
      className={`group relative grid min-h-11.5 min-w-0 cursor-pointer grid-cols-[minmax(0,1fr)_auto] items-center gap-3 rounded-xl border px-3 py-2 text-left transition-[background-color,border-color,opacity] duration-200 focus-visible:z-90 hover:z-100 focus-visible:outline-2 focus-visible:outline-emerald-300 disabled:cursor-not-allowed disabled:opacity-45 ${checked ? "border-emerald-200/75 bg-emerald-500/20 hover:border-emerald-100/90 hover:bg-emerald-400/25" : "border-white/10 bg-black/10 hover:border-emerald-200/35 hover:bg-white/6"} ${className || ""}`}
      aria-pressed={checked}
      disabled={disabled}
      onClick={onClick}
    >
      <span className="min-w-0">
        <span className="block text-sm font-black text-neutral-100">{label}</span>
        {description ? <Tooltip>{description}</Tooltip> : null}
      </span>
      <span className="flex shrink-0 items-center gap-3">
        {status}
        <Toggle checked={checked} />
      </span>
    </button>
  );
}

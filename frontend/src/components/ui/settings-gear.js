import { FiSettings } from "react-icons/fi";

import Tooltip from "@/components/ui/tooltip";

export default function SettingsGear({ label, open, onClick, className }) {
  const actionLabel = `${open ? "關閉" : "開啟"}設定`;

  return (
    <button 
    className={`group relative inline-grid size-10 shrink-0 cursor-pointer place-items-center rounded-xl border transition-[background-color,border-color,color] duration-150 
              hover:border-emerald-200/50 hover:bg-emerald-400/15 hover:text-emerald-100 focus-visible:outline-2 focus-visible:outline-emerald-300 
              ${open ? "border-emerald-200/60 bg-emerald-400/20 text-emerald-100" : "border-white/15 bg-white/6 text-white/75"} 
              ${className || ""}`} type="button" aria-label={`${actionLabel}${label}`} 
    aria-expanded={open} onClick={onClick}
    >
      <FiSettings className={`size-5 transition group-hover:rotate-12 ${open ? "rotate-30" : "rotate-0"}`} aria-hidden="true" />
      <Tooltip className="top-[calc(100%+0.5rem)] right-0 left-auto">{actionLabel}</Tooltip>
    </button>
  );
}

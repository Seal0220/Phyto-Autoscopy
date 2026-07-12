import { PiPlantFill } from "react-icons/pi";

import Button from "@/components/buttons/Button";
import NavLink from "@/components/navigation/NavLink";

const NAV_ITEMS = [
  ["image-preview", "影像預覽"],
  ["overview", "即時狀態"],
  ["schedule", "排程"],
  ["motor", "控制"],
  ["records-storage", "紀錄與儲存"],
];

export default function Header({
  actor,
  isConnected,
  emergencyStopping,
  onEmergencyStop,
  onLogout,
}) {
  return (
    <aside className="fixed inset-x-0 top-0 z-[200] grid min-h-[4.25rem] grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] items-center gap-4 border-b border-white/10 bg-[#07110d]/80 px-5 py-3 shadow-[0_14px_42px_rgba(0,0,0,0.14)] backdrop-blur-2xl max-[980px]:grid-cols-[minmax(0,1fr)_auto] max-[980px]:gap-2 max-[980px]:px-3 max-[980px]:py-2">
      <div className="grid min-w-0 grid-cols-[2.25rem_minmax(0,1fr)] items-center gap-3">
        <span
          className="grid size-9 place-items-center rounded-2xl border border-emerald-200/20 bg-emerald-300/10"
          aria-hidden="true"
        >
          <PiPlantFill className="size-5 text-emerald-200" />
        </span>
        <div className="min-w-0">
          <strong className="block overflow-hidden text-sm font-black tracking-[0.08em] text-white text-ellipsis whitespace-nowrap">PHYTO-AUTOSCOPY</strong>
          <span className="block pt-0.5 text-[11px] font-bold text-neutral-300">控制台</span>
        </div>
      </div>
      <nav className="flex min-w-0 items-center gap-1 overflow-x-auto rounded-2xl border border-white/10 bg-black/10 p-1 max-[980px]:col-span-full max-[980px]:row-start-2 max-[980px]:w-full" aria-label="主要導覽">
        {NAV_ITEMS.map(([id, label]) => <NavLink href={`#${id}`} key={id}>{label}</NavLink>)}
      </nav>
      <div className="col-start-3 flex min-w-0 items-center justify-end gap-2 max-[980px]:col-start-2 max-[980px]:row-start-1">
        <span className={`inline-flex min-h-8 items-center rounded-full border px-3 text-xs font-black max-[720px]:hidden ${isConnected ? "border-emerald-200/60 bg-emerald-500/15 text-emerald-200" : "border-amber-200/60 bg-amber-500/15 text-amber-200"}`}>{isConnected ? "即時連線已建立" : "即時連線中"}</span>
        <Button className="min-h-9 px-3 text-xs" variant="danger" disabled={!isConnected || emergencyStopping} onClick={onEmergencyStop}>緊急停止</Button>
        <Button className="min-h-9 px-2 text-xs" variant="ghost" onClick={onLogout}>登出 {actor}</Button>
      </div>
    </aside>
  );
}

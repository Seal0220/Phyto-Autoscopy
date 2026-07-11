"use client";

import { useEffect } from "react";
import Button from "@/components/ui/button";

export default function ToastViewport({ toast, onClose }) {
  useEffect(() => {
    if (!toast) return undefined;
    const timer = window.setTimeout(onClose, 4500);
    return () => window.clearTimeout(timer);
  }, [toast, onClose]);

  if (!toast) return null;

  const tone = toast.tone === "success" ? "border-l-emerald-300" : toast.tone === "error" ? "border-l-rose-400" : "border-l-slate-400";

  return (
    <div className={`fixed right-5 bottom-5 z-50 flex w-[min(24rem,calc(100vw-2.5rem))] items-start gap-3 rounded-xl border border-white/20 border-l-[3px] bg-[#08140f]/95 px-4 py-3 text-slate-100 shadow-2xl backdrop-blur-xl motion-safe:animate-[fade-in_180ms_ease-out] ${tone}`} role="status" aria-live="polite">
      <p className="flex-1 text-sm leading-6">{toast.message}</p>
      <Button className="grid size-6 min-h-6 place-items-center rounded-md p-0 text-xl leading-none" variant="ghost" aria-label="關閉通知" onClick={onClose}>×</Button>
    </div>
  );
}

"use client";

import { useRef } from "react";
import { StatusPill } from "@/components/panels/Panel";

export default function AnalysisRunRoundList({
  items,
  selectedRoundKey,
  idPrefix,
  contentId,
  onSelect,
}) {
  const list = useRef(null);

  function handleKeyDown(
    event,
    index,
  ) {
    let nextIndex;
    if (event.key === "ArrowDown") nextIndex = (index + 1) % items.length;
    else if (event.key === "ArrowUp") nextIndex = (index - 1 + items.length) % items.length;
    else if (event.key === "Home") nextIndex = 0;
    else if (event.key === "End") nextIndex = items.length - 1;
    else return;

    event.preventDefault();
    onSelect(items[nextIndex].roundKey);
    const button = list.current?.querySelectorAll('[role="tab"]')[nextIndex];
    if (!button) return;

    button.focus({ preventScroll: true });
    const buttonBounds = button.getBoundingClientRect();
    const listBounds = list.current.getBoundingClientRect();
    if (buttonBounds.top < listBounds.top) {
      list.current.scrollTop += buttonBounds.top - listBounds.top;
    } else if (buttonBounds.bottom > listBounds.bottom) {
      list.current.scrollTop += buttonBounds.bottom - listBounds.bottom;
    }
  }

  return (
    <div
      ref={list}
      role="tablist"
      aria-label="分析輪次"
      aria-orientation="vertical"
      className="min-h-0 min-w-0 overflow-x-hidden overflow-y-auto overscroll-contain rounded-xl border border-white/15 bg-black/15 p-2 [scrollbar-gutter:stable] max-sm:p-1"
    >
      <div className="grid min-w-0 content-start gap-1.5">
        {items.map((item, index) => {
          const selected = item.roundKey === selectedRoundKey;
          return (
            <button
              key={item.roundKey}
              id={`${idPrefix}-${encodeURIComponent(item.roundKey)}`}
              type="button"
              role="tab"
              aria-selected={selected}
              aria-controls={contentId}
              tabIndex={selected ? 0 : -1}
              onClick={() => onSelect(item.roundKey)}
              onKeyDown={(event) => handleKeyDown(event, index)}
              className={`grid min-w-0 cursor-pointer content-start gap-1.5 rounded-xl border px-3 py-2 text-left transition-[background-color,border-color,color] duration-150 focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-emerald-300 max-sm:px-1.5
                ${selected
                  ? "border-emerald-200/40 bg-emerald-400/15 text-emerald-100 hover:border-emerald-100/60 hover:bg-emerald-300/20"
                  : "border-white/15 bg-black/15 text-neutral-200 hover:border-white/25 hover:bg-white/[0.07]"
                }`}
            >
              <span className="flex min-w-0 flex-wrap items-baseline gap-x-1 text-xs">
                <span className="min-w-0 break-all font-semibold text-neutral-400">{item.modeId} ·</span>
                <span className="min-w-0 break-all font-black">{item.roundId}</span>
              </span>
              <span className="flex min-w-0 flex-wrap items-center gap-1">
                {item.status ? (
                  <StatusPill
                    tone={item.status.tone}
                    compact
                  >
                    {item.status.label}
                  </StatusPill>
                ) : null}
                {item.modelStatus ? (
                  <StatusPill
                    tone={item.modelStatus.tone}
                    compact
                  >
                    {item.modelStatus.label}
                  </StatusPill>
                ) : null}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}

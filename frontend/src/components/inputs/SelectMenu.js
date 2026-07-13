"use client";

import {
  useEffect,
  useRef,
  useState,
} from "react";
import { FiChevronDown } from "react-icons/fi";

export default function SelectMenu({
  id,
  value,
  options,
  onValueChange,
  className,
}) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef(null);
  const menuId = `${id}-options`;

  useEffect(() => {
    function closeWhenOutside(event) {
      if (!rootRef.current?.contains(event.target)) setOpen(false);
    }
    function closeOnEscape(event) {
      if (event.key === "Escape") setOpen(false);
    }
    document.addEventListener("pointerdown", closeWhenOutside);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("pointerdown", closeWhenOutside);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, []);

  return (
    <div
      className="relative"
      ref={rootRef}
    >
      <button
        id={id}
        className={`
          flex min-h-10.5 w-full cursor-pointer items-center justify-between rounded-xl border bg-black/15 px-3 pt-3 pb-2 text-left text-sm font-bold text-white outline-none transition-[background-color,border-color,box-shadow] duration-150 hover:border-emerald-200/45 hover:bg-white/[0.06] focus:border-emerald-300/60 focus:bg-white/[0.06] focus:ring-4 focus:ring-emerald-300/10
          ${className || ""}
          ${
            open
              ? "border-emerald-200/60 bg-emerald-400/10 hover:border-emerald-200/75 hover:bg-emerald-400/15"
              : "border-white/15"
          }
        `}
        type="button"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={menuId}
        onClick={() => setOpen((current) => !current)}
      >
        <span>{value}</span>
        <FiChevronDown
          className={`
            size-4 shrink-0 text-neutral-400 transition-transform duration-150
            ${open ? "rotate-180" : ""}
          `}
          aria-hidden="true"
        />
      </button>
      <div
        id={menuId}
        role="listbox"
        className={`
          absolute top-[calc(100%+0.4rem)] left-0 z-[120] grid w-full overflow-hidden rounded-xl border border-white/15 bg-[#07130f]/95 p-1 shadow-2xl backdrop-blur-xl transition-opacity duration-150
          ${open ? "opacity-100" : "pointer-events-none opacity-0"}
        `}
        aria-hidden={!open}
        inert={!open}
      >
        {options.map((option) => (
          <button
            className={`
              cursor-pointer rounded-lg px-3 py-2 text-left text-sm font-bold transition-colors duration-150 hover:bg-emerald-400/15 hover:text-emerald-100
              ${option === value ? "bg-white/10 text-white" : "text-neutral-300"}
            `}
            type="button"
            role="option"
            aria-selected={option === value}
            tabIndex={open ? 0 : -1}
            key={option}
            onClick={() => {
              onValueChange(option);
              setOpen(false);
            }}
          >
            {option}
          </button>
        ))}
      </div>
    </div>
  );
}

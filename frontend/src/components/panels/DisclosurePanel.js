import { FiChevronDown } from "react-icons/fi";

export default function DisclosurePanel({
  children,
  description,
  title,
}) {
  return (
    <details className="group min-w-0 rounded-xl border border-white/15 bg-black/15">
      <summary className="grid min-h-12 cursor-pointer list-none grid-cols-[minmax(0,1fr)_auto] items-center gap-3 px-4 py-3 focus-visible:outline-2 focus-visible:outline-emerald-300 [&::-webkit-details-marker]:hidden">
        <span className="grid min-w-0 gap-1">
          <span className="text-sm font-black text-neutral-100">{title}</span>
          {description ? (
            <span className="text-xs font-semibold text-neutral-400">
              {description}
            </span>
          ) : null}
        </span>
        <FiChevronDown
          className="size-4 shrink-0 text-neutral-300 transition-transform duration-150 group-open:rotate-180 motion-reduce:transition-none"
          aria-hidden="true"
        />
      </summary>
      <div className="grid gap-4 border-t border-white/15 p-4">
        {children}
      </div>
    </details>
  );
}

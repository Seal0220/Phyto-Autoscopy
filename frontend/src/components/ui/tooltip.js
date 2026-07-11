export default function Tooltip({ children, className }) {
  return <span className={`pointer-events-none absolute top-[calc(100%+0.5rem)] left-0 z-[110] w-max max-w-[min(22rem,calc(100vw-2rem))] rounded-lg border border-white/15 bg-[#07130f]/95 px-3 py-2 text-xs font-semibold leading-5 text-white/80 opacity-0 shadow-xl backdrop-blur-xl transition-opacity duration-150 delay-150 group-hover:opacity-100 group-hover:delay-0 ${className || ""}`}>{children}</span>;
}

export default function Toggle({ checked, className }) {
  return (
    <span className={`relative h-6 w-10.5 rounded-full border transition duration-200 ease-in-out motion-reduce:transition-none ${checked ? "border-emerald-200/60 bg-emerald-500/60" : "border-white/20 bg-white/10"} ${className || ""}`} aria-hidden="true">
      <span className={`absolute top-0.5 left-0.5 size-4.5 rounded-full bg-white/75 transition duration-200 ease-in-out motion-reduce:transition-none ${checked ? "translate-x-4.5 bg-white" : "translate-x-0"}`} />
    </span>
  );
}

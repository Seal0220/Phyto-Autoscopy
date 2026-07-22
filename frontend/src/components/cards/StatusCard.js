export default function StatusCard({
  title,
  content,
  note,
  className,
  ...props
}) {
  return (
    <article
      className={`flex min-w-0 flex-col content-start justify-between gap-1 rounded-xl border border-white/15 bg-white/6 p-3 shadow-[inset_0_1px_0_rgba(255,255,255,0.05)] ${className || ""}`}
      {...props}
    >
      <h3 className="m-0 text-sm font-black tracking-widest text-emerald-200">{title}</h3>
      <div className="min-w-0 w-full wrap-break-word p-4 text-center text-2xl font-semibold leading-5 text-white">
        {content}
      </div>
      <div className="ml-auto text-xs font-semibold text-neutral-300">{note}</div>
    </article>
  );
}

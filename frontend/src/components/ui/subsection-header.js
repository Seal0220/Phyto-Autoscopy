const TITLE_STYLES = {
  0: "text-base font-black tracking-widest text-white",
  1: "text-sm font-black tracking-widest text-emerald-200",
};

export default function SubsectionHeader({ children, className, description, title, titleId, titleMode = 0, ...props }) {
  return (
    <header className={`grid min-w-0 grid-cols-[minmax(0,1fr)_auto] items-start gap-3 px-1 ${className || ""}`} {...props}>
      <div className="min-w-0">
        <h3 id={titleId} className={`m-0 ${TITLE_STYLES[titleMode] || TITLE_STYLES[0]}`}>{title}</h3>
        {description ? <p className="mt-1 text-xs font-semibold text-neutral-400">{description}</p> : null}
      </div>
      {children ? <div className="flex shrink-0 items-center self-start">{children}</div> : null}
    </header>
  );
}

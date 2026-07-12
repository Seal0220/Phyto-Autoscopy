import ActionRow from "@/components/actions/ActionRow";

export default function SettingPanel({
  children,
  label,
  open = false,
  locked = false,
  footer,
  footerClassName = "px-6 pb-6",
  footerDividerClassName,
  className,
  contentClassName,
  fieldsetClassName,
}) {
  return (
    <section
      className={`grid transition-[grid-template-rows,opacity] duration-200 ease-out motion-reduce:transition-none ${open ? "grid-rows-[1fr] opacity-100" : "pointer-events-none grid-rows-[0fr] opacity-0"} ${className || ""}`}
      aria-label={`${label}設定`}
      aria-hidden={!open}
    >
      <div className={`min-h-0 ${open ? "overflow-visible" : "overflow-hidden"}`}>
        <div className={`rounded-b-[27px] border-t border-white/10 bg-black/20 ${contentClassName || "px-6 pt-6 max-sm:px-4"}`}>
          <fieldset
            className={`grid min-w-0 border-0 p-0 ${fieldsetClassName || "gap-4"} ${locked ? "grayscale opacity-60" : ""}`}
            disabled={locked}
          >
            {children}
            {footer ? (
              <ActionRow
                className={footerClassName}
                dividerClassName={footerDividerClassName}
              >
                {footer}
              </ActionRow>
            ) : null}
          </fieldset>
        </div>
      </div>
    </section>
  );
}

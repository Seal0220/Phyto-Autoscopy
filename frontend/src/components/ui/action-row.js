export default function ActionRow({
  children,
  className,
  ...props
}) {
  return (
    <>
      <hr className="mb-0!" />
      <div
        className={`place-self-end flex flex-wrap items-center pt-2 gap-2 ${className || ""}`}
        {...props}
      >
        {children}
      </div>
    </>
  );
}

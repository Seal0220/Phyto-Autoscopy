export default function VerticalLine({ className }) {
  return (
    <div
      className={`mx-2 h-8 w-px place-self-center bg-white/10 ${className || ""}`}
      aria-hidden="true"
    />
  );
}

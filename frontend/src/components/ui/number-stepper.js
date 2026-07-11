import { FiChevronDown, FiChevronUp } from "react-icons/fi";

export default function NumberStepper({ label, onIncrement, onDecrement }) {
  return (
    <span className="absolute top-1 right-0 grid h-[46px] w-9 overflow-hidden rounded-r-xl border-l border-white/15 bg-white/[0.07]">
      <button className="grid cursor-pointer place-items-center border-b border-white/15 text-white/75 transition-colors duration-150 hover:bg-white/15" type="button" aria-label={`增加${label}`} onClick={onIncrement}><FiChevronUp aria-hidden="true" /></button>
      <button className="grid cursor-pointer place-items-center text-white/75 transition-colors duration-150 hover:bg-white/15" type="button" aria-label={`減少${label}`} onClick={onDecrement}><FiChevronDown aria-hidden="true" /></button>
    </span>
  );
}

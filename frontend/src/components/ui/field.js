import { Input } from "@/components/ui/input";
import NumberStepper from "@/components/ui/number-stepper";
import SelectMenu from "@/components/ui/select-menu";
import Tooltip from "@/components/ui/tooltip";

function FieldFrame({ label, children, description }) {
  return (
    <div className="group relative min-w-0 focus-within:z-[90] hover:z-[100]">
      <div className="relative min-w-0 pt-1">
        <span className="pointer-events-none absolute top-0 left-3 z-10 text-xs font-black leading-none text-white/75">{label}</span>
        {children}
      </div>
      {description ? <Tooltip>{description}</Tooltip> : null}
    </div>
  );
}

export function NumericField({ id, label, value, onValueChange, min, max, step = 1, suffix, description, required = false }) {
  function adjust(direction) {
    const current = Number(value);
    const fallback = min ?? 0;
    const next = Math.min(max ?? Number.POSITIVE_INFINITY, Math.max(min ?? Number.NEGATIVE_INFINITY, (Number.isFinite(current) ? current : fallback) + direction * Number(step)));
    const decimals = String(step).includes(".") ? String(step).split(".")[1].length : 0;
    onValueChange(String(Number(next.toFixed(decimals))));
  }

  return (
    <FieldFrame label={label} description={description}>
      <Input id={id} className={`min-h-[46px] border-white/15 pt-4 pb-2 font-bold ${suffix ? "pr-[6.5rem]" : "pr-12"}`} type="text" inputMode="decimal" value={String(value ?? "")} onChange={(event) => onValueChange(event.target.value)} required={required} />
      {suffix ? <span className="pointer-events-none absolute top-1/2 right-11 -translate-y-1/2 text-xs font-extrabold text-white/50">{suffix}</span> : null}
      <NumberStepper label={label} onIncrement={() => adjust(1)} onDecrement={() => adjust(-1)} />
    </FieldFrame>
  );
}

export function TextField({ id, label, value, onValueChange, type = "text", autoComplete, required = false, description, ...inputProps }) {
  const valueProps = onValueChange ? { value: value ?? "", onChange: (event) => onValueChange(event.target.value) } : {};
  return (
    <FieldFrame label={label} description={description}>
      <Input id={id} className="min-h-[46px] border-white/15 pt-4 pb-2 font-bold" type={type} autoComplete={autoComplete} required={required} {...valueProps} {...inputProps} />
    </FieldFrame>
  );
}

export function SelectField({ id, label, value, onValueChange, options, description }) {
  return (
    <FieldFrame label={label} description={description}>
      <SelectMenu id={id} className="border-white/15" value={String(value ?? "")} options={options} onValueChange={onValueChange} />
    </FieldFrame>
  );
}

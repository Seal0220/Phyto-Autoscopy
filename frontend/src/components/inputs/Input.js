import { FiChevronDown, FiChevronUp } from "react-icons/fi";

import { FieldFrame } from "@/components/fields/FieldFrame";
import SelectMenu from "@/components/inputs/SelectMenu";
import { durationParts, durationValue } from "@/lib/durationUtils";

function NumberStepper({
  label,
  onIncrement,
  onDecrement,
  disabled = false,
  className,
}) {
  return (
    <span
      className={`
        grid w-9 overflow-hidden border-l border-white/15 bg-white/7
        ${className || ""}
      `}
    >
      <button
        className="grid cursor-pointer place-items-center border-b border-white/15 text-neutral-300 transition-colors duration-150 hover:bg-white/15 disabled:cursor-not-allowed disabled:text-neutral-600 disabled:hover:bg-transparent"
        type="button"
        aria-label={`增加${label}`}
        disabled={disabled}
        onClick={onIncrement}
      >
        <FiChevronUp aria-hidden="true" />
      </button>
      <button
        className="grid cursor-pointer place-items-center text-neutral-300 transition-colors duration-150 hover:bg-white/15 disabled:cursor-not-allowed disabled:text-neutral-600 disabled:hover:bg-transparent"
        type="button"
        aria-label={`減少${label}`}
        disabled={disabled}
        onClick={onDecrement}
      >
        <FiChevronDown aria-hidden="true" />
      </button>
    </span>
  );
}

export function Input({
  className,
  containerClassName,
  label,
  onChange,
  onValueChange,
  stepperClassName,
  suffix,
  type,
  value,
  min,
  max,
  step = 1,
  ...props
}) {
  const isNumber = type === "number";
  const disabled = Boolean(props.disabled);

  function adjust(direction) {
    if (disabled) return;

    const current = Number(value);
    const fallback = min ?? 0;
    const next = Math.min(
      max ?? Number.POSITIVE_INFINITY,
      Math.max(
        min ?? Number.NEGATIVE_INFINITY,
        (Number.isFinite(current) ? current : fallback) + direction * Number(step),
      ),
    );
    const decimals = String(step).includes(".")
      ? String(step).split(".")[1].length
      : 0;
    onValueChange?.(String(Number(next.toFixed(decimals))));
  }

  return (
    <div
      className={`
        h-10.5 min-w-0
        ${isNumber ? (
          suffix
            ? "grid grid-cols-[minmax(0,1fr)_auto_2.25rem] rounded-xl border border-white/15 bg-black/15 overflow-hidden transition hover:border-white/20 focus-within:border-emerald-300/60 focus-within:ring-4 focus-within:ring-emerald-300/10"
            : "grid grid-cols-[minmax(0,1fr)_2.25rem] rounded-xl border border-white/15 bg-black/15 transition hover:border-white/20 focus-within:border-emerald-300/60 focus-within:ring-4 focus-within:ring-emerald-300/10"
        ) : "relative"}
        ${containerClassName || ""}
      `}
    >
      <input
        className={`
          min-w-0 w-full rounded-xl border border-white/15 bg-black/15 px-3 py-2 text-sm font-semibold text-white outline-none transition
          ${
            isNumber
              ? "rounded-none! border-0! bg-transparent appearance-none [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none [-moz-appearance:textfield]"
              : "hover:border-white/20 focus:border-emerald-300/60 focus:ring-4 focus:ring-emerald-300/10"
          }
          ${className || ""}
        `}
        type={type}
        value={value}
        min={min}
        max={max}
        step={step}
        onChange={(event) => {
          onValueChange?.(event.target.value);
          onChange?.(event);
        }}
        {...props}
      />
      {suffix ? (
        <span
          className={
            isNumber
              ? "pointer-events-none flex shrink-0 items-center pr-2 text-xs font-extrabold whitespace-nowrap text-neutral-500 select-none"
              : "pointer-events-none absolute top-1/2 right-3 -translate-y-1/2 text-xs font-extrabold text-neutral-500 select-none"
          }
        >
          {suffix}
        </span>
      ) : null}
      {isNumber ? (
        <NumberStepper
          label={label || "數值"}
          disabled={disabled}
          onIncrement={() => adjust(1)}
          onDecrement={() => adjust(-1)}
          className={stepperClassName}
        />
      ) : null}
    </div>
  );
}

export function NumericInput({
  id,
  label,
  disabled = false,
  value,
  onValueChange,
  min,
  max,
  step = 1,
  suffix,
  description,
  required = false,
  className,
}) {
  return (
    <FieldFrame
      label={label}
      description={description}
      className={className}
    >
      <Input
        id={id}
        className="min-h-10.5 pt-3 pb-2 font-bold"
        containerClassName="border-white/15"
        label={label}
        disabled={disabled}
        type="number"
        inputMode="decimal"
        min={min}
        max={max}
        step={step}
        value={String(value ?? "")}
        onValueChange={onValueChange}
        required={required}
        suffix={suffix}
      />
    </FieldFrame>
  );
}

export function DurationInput({
  id,
  label,
  value,
  onValueChange,
  unit = "seconds",
  description,
  required = false,
  className,
}) {
  const parts = durationParts(value, unit);

  function updatePart(
    part,
    nextValue,
  ) {
    const parsed = Number(nextValue);
    const nextParts = {
      ...parts,
      [part]: Number.isFinite(parsed) && parsed >= 0 ? parsed : 0,
    };
    onValueChange(durationValue(nextParts, unit));
  }

  return (
    <FieldFrame
      label={label}
      description={description}
      className={className}
    >
      <div className="relative grid min-w-0 grid-cols-4">
        <Input
          id={`${id}-days`}
          className="min-h-10.5 pt-3 pb-2 font-bold"
          containerClassName="rounded-r-none! border-white/15 focus-within:z-10"
          label={`${label}天`}
          type="number"
          inputMode="decimal"
          min={0}
          step={1}
          value={String(parts.days)}
          onValueChange={(nextValue) => updatePart("days", nextValue)}
          required={required}
          suffix="天"
          stepperClassName="rounded-none!"
        />
        <Input
          id={`${id}-hours`}
          className="min-h-10.5 pt-3 pb-2 font-bold"
          containerClassName="rounded-none! border-l-0! border-white/15 focus-within:z-10"
          label={`${label}時`}
          type="number"
          inputMode="decimal"
          min={0}
          max={23}
          step={1}
          value={String(parts.hours)}
          onValueChange={(nextValue) => updatePart("hours", nextValue)}
          required={required}
          suffix="時"
          stepperClassName="rounded-none!"
        />
        <Input
          id={`${id}-minutes`}
          className="min-h-10.5 pt-3 pb-2 font-bold"
          containerClassName="rounded-none! border-l-0! border-white/15 focus-within:z-10"
          label={`${label}分`}
          type="number"
          inputMode="decimal"
          min={0}
          max={59}
          step={1}
          value={String(parts.minutes)}
          onValueChange={(nextValue) => updatePart("minutes", nextValue)}
          required={required}
          suffix="分"
          stepperClassName="rounded-none!"
        />
        <Input
          id={`${id}-seconds`}
          className="min-h-10.5 pt-3 pb-2 font-bold"
          containerClassName="rounded-l-none! border-l-0! border-white/15 focus-within:z-10"
          label={`${label}秒`}
          type="number"
          inputMode="decimal"
          min={0}
          max={59}
          step={1}
          value={String(parts.seconds)}
          onValueChange={(nextValue) => updatePart("seconds", nextValue)}
          required={required}
          suffix="秒"
        />
      </div>
    </FieldFrame>
  );
}

export function TextInput({
  id,
  label,
  value,
  onValueChange,
  type = "text",
  autoComplete,
  required = false,
  description,
  ...inputProps
}) {
  const valueProps = {
    ...(value !== undefined
      ? {
        value: value ?? "",
      }
      : {}),
    ...(onValueChange
      ? {
        onChange: (event) => onValueChange(event.target.value),
      }
      : {}),
  };

  return (
    <FieldFrame
      label={label}
      description={description}
    >
      <Input
        id={id}
        className="min-h-10.5 border-white/15 pt-3 pb-2 font-bold"
        type={type}
        autoComplete={autoComplete}
        required={required}
        {...valueProps}
        {...inputProps}
      />
    </FieldFrame>
  );
}

export function SelectInput({
  id,
  label,
  value,
  onValueChange,
  options,
  description,
  className,
}) {
  return (
    <FieldFrame
      label={label}
      description={description}
      className={className}
    >
      <SelectMenu
        id={id}
        className="border-white/15"
        value={String(value ?? "")}
        options={options}
        onValueChange={onValueChange}
      />
    </FieldFrame>
  );
}

export function Select({
  className,
  children,
  ...props
}) {
  return (
    <select
      className={`
        min-h-10 w-full rounded-xl border border-white/15 bg-black/15 px-3 py-2 text-sm font-semibold text-white outline-none transition hover:border-white/20 focus:border-emerald-300/60 focus:ring-4 focus:ring-emerald-300/10 appearance-none
        ${className || ""}
      `}
      {...props}
    >
      {children}
    </select>
  );
}

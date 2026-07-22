import Tooltip from "@/components/Tooltip";

const VALUE_TONE_CLASSES = {
  success: "text-emerald-200",
  warning: "text-amber-200",
  error: "text-rose-200",
  neutral: "text-neutral-500",
};

const BORDER_CLASSES = {
  none: "",
  top: "border-t border-white/15 pt-3",
  both: "border-y border-white/15 py-3",
};

function columnSpacing(
  index,
  columnCount,
  stackAtSmall,
  configuredColumnCount,
) {
  const visualColumnCount = configuredColumnCount || columnCount;
  const columnPosition = index % visualColumnCount;
  const first = columnPosition === 0;
  const last = columnPosition === visualColumnCount - 1
    || index === columnCount - 1;

  if (columnCount === 1) return "px-2";
  if (stackAtSmall) {
    if (first) return "px-2 min-[520px]:pl-2 min-[520px]:pr-3";
    if (last) {
      return `
        px-2
        min-[520px]:border-l min-[520px]:border-white/15
        min-[520px]:pl-3 min-[520px]:pr-2
      `;
    }
    return `
      px-2
      min-[520px]:border-l min-[520px]:border-white/15 min-[520px]:px-3
    `;
  }
  if (first) return "pl-2 pr-3";
  if (last) return "border-l border-white/15 pl-3 pr-2";
  return "border-l border-white/15 px-3";
}

function layoutCount(
  value,
  fallback,
) {
  const number = Number(value);

  return Number.isInteger(number) && number > 0
    ? number
    : fallback;
}

export default function InformationGrid({
  items = [],
  rows,
  columns,
  border = "top",
  scroll = false,
  minimumColumnWidth = false,
  stackAtSmall = false,
  className,
  ariaLabel,
}) {
  if (items.length === 0) return null;

  const requestedRowCount = layoutCount(rows, null);
  const requestedColumnCount = layoutCount(columns, null);
  const rowCount = requestedRowCount
    || (requestedColumnCount
      ? Math.ceil(items.length / requestedColumnCount)
      : 2
    );
  const requiredColumnCount = Math.ceil(items.length / rowCount);
  const columnCount = requestedColumnCount
    ? Math.max(requestedColumnCount, requiredColumnCount)
    : requiredColumnCount;
  const itemColumns = [];

  for (let index = 0; index < items.length; index += rowCount) {
    itemColumns.push(items.slice(index, index + rowCount));
  }

  return (
    <div
      className={`
        min-w-0
        ${BORDER_CLASSES[border] || BORDER_CLASSES.top}
        ${scroll ? "overflow-x-auto overscroll-x-contain" : ""}
        ${className || ""}
      `}
      aria-label={ariaLabel}
      role={ariaLabel ? "group" : undefined}
    >
      <div
        className={`
          grid min-w-0
          ${stackAtSmall
            ? "gap-y-2 min-[520px]:grid-cols-[repeat(var(--information-columns),minmax(0,1fr))]"
            : minimumColumnWidth
              ? "grid-cols-[repeat(var(--information-columns),minmax(11rem,1fr))]"
              : "grid-cols-[repeat(var(--information-columns),minmax(0,1fr))]"
          }
        `}
        style={{
          "--information-columns": columnCount,
        }}
      >
        {itemColumns.map((column, columnIndex) => (
          <dl
            className={`grid grid-rows-[repeat(var(--information-rows),minmax(0,auto))] gap-y-2 ${columnSpacing(
              columnIndex,
              itemColumns.length,
              stackAtSmall,
              columnCount,
            )}`}
            key={column[0].label}
            style={{
              "--information-rows": rowCount,
            }}
          >
            {column.map((item) => (
              <div
                className="flex min-h-6 min-w-0 items-center justify-between gap-2"
                key={item.label}
              >
                <dt
                  className={`relative min-w-0 whitespace-nowrap ${item.requirement ? "group cursor-help" : ""}`}
                >
                  <span className="text-xs font-bold text-neutral-200">
                    {item.label}
                  </span>
                  {item.requirement ? (
                    <Tooltip>
                      {item.requirement}
                    </Tooltip>
                  ) : null}
                </dt>
                <dd
                  className={`m-0 flex items-baseline gap-1 ${item.truncate ? "min-w-0" : "shrink-0"}`}
                >
                  <span
                    className={`
                      text-right text-xs font-black
                      ${item.truncate ? "min-w-0 truncate" : ""}
                      ${VALUE_TONE_CLASSES[item.tone] || VALUE_TONE_CLASSES.success}
                    `}
                  >
                    {item.value}
                  </span>
                </dd>
              </div>
            ))}
          </dl>
        ))}
      </div>
    </div>
  );
}

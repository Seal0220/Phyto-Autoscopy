import {
  formatCalibrationNumber,
} from "../lib/calibrationUtils";

function matrixRows(value) {
  if (!Array.isArray(value)) return [];
  if (!value.length) return [];
  return Array.isArray(value[0]) ? value : [value];
}

export default function CalibrationMatrix({
  title,
  value,
  description,
}) {
  const rows = matrixRows(value);
  const columnCount = Math.max(
    1,
    ...rows.map((row) => row.length),
  );

  return (
    <article className="grid min-w-0 content-start gap-3 rounded-xl border border-white/10 bg-black/10 p-3">
      <div className="min-w-0">
        <h4 className="m-0 text-xs font-black text-emerald-200">{title}</h4>
        {description ? (
          <p className="mt-1 text-[11px] font-semibold text-neutral-400">
            {description}
          </p>
        ) : null}
      </div>
      {rows.length ? (
        <div className="overflow-x-auto rounded-lg border border-white/10 bg-black/15 p-2">
          <table className="min-w-full border-separate border-spacing-px overflow-hidden rounded-lg bg-white/10">
            <tbody>
              {rows.map((row, rowIndex) => (
                <tr key={rowIndex}>
                  {Array.from(
                    {
                      length: columnCount,
                    },
                    (_, columnIndex) => (
                      <td
                        className="min-w-26 bg-[#0b1813] px-2 py-1.5 text-right font-mono text-xs font-semibold text-neutral-200 tabular-nums"
                        key={columnIndex}
                      >
                        {columnIndex < row.length
                          ? formatCalibrationNumber(row[columnIndex], 9)
                          : "—"
                        }
                      </td>
                    ),
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="m-0 text-sm font-semibold text-neutral-500">尚未產生</p>
      )}
    </article>
  );
}

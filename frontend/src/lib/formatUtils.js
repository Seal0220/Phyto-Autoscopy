export function formatElapsed(seconds) {
  const value = Math.max(0, Number(seconds) || 0);
  const days = Math.floor(value / 86400);
  const hours = Math.floor((value % 86400) / 3600);
  const minutes = Math.floor((value % 3600) / 60);
  const remainingSeconds = Math.floor(value % 60);
  const paddedHours = String(hours).padStart(2, "0");
  const paddedMinutes = String(minutes).padStart(2, "0");
  const paddedSeconds = String(remainingSeconds).padStart(2, "0");
  if (days) return `${days} 天 ${paddedHours} 時 ${paddedMinutes} 分 ${paddedSeconds} 秒`;
  if (hours) return `${paddedHours} 時 ${paddedMinutes} 分 ${paddedSeconds} 秒`;
  if (minutes) return `${paddedMinutes} 分 ${paddedSeconds} 秒`;
  return `${paddedSeconds} 秒`;
}

function hasDisplayValue(value) {
  return value !== null
    && value !== undefined
    && value !== "";
}

export function formatNumberWithUnit(
  value,
  unit,
) {
  if (!hasDisplayValue(value)) return "尚無資料";

  const number = Number(value);

  return Number.isFinite(number)
    ? `${Number(number.toFixed(3))} ${unit}`
    : "尚無資料";
}

export function formatOptionalElapsed(value) {
  if (!hasDisplayValue(value)) return "尚無資料";

  const seconds = Number(value);

  return Number.isFinite(seconds)
    ? formatElapsed(seconds)
    : "尚無資料";
}

export function formatBooleanState(value) {
  if (value === true) return "啟用";
  if (value === false) return "關閉";
  return "尚無資料";
}

export function formatRangeWithUnit(
  start,
  end,
  unit,
) {
  const startNumber = Number(start);
  const endNumber = Number(end);

  if (
    !hasDisplayValue(start)
    || !hasDisplayValue(end)
    || !Number.isFinite(startNumber)
    || !Number.isFinite(endNumber)
  ) {
    return "尚無資料";
  }

  return `${formatNumberWithUnit(startNumber, unit)} – ${formatNumberWithUnit(endNumber, unit)}`;
}

export function formatBytes(value) {
  if (!Number.isFinite(value)) return "—";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let unit = 0;
  let amount = value;
  while (amount >= 1024 && unit < units.length - 1) {
    amount /= 1024;
    unit += 1;
  }
  return `${amount.toFixed(unit === 0 ? 0 : 1)} ${units[unit]}`;
}

export function formatDateTime(value) {
  if (!value) return "—";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString("zh-TW", { hour12: false });
}

export function formatClockTime(timestamp) {
  return new Intl.DateTimeFormat("zh-TW", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(timestamp);
}

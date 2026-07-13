const DURATION_UNIT_SECONDS = {
  milliseconds: 0.001,
  minutes: 60,
  seconds: 1,
};

export function durationParts(
  value,
  unit,
) {
  const totalSeconds = Math.max(0, Number(value) || 0)
    * (DURATION_UNIT_SECONDS[unit] || DURATION_UNIT_SECONDS.seconds);
  const roundedSeconds = Number(totalSeconds.toFixed(3));
  const days = Math.floor(roundedSeconds / 86400);
  const hours = Math.floor((roundedSeconds % 86400) / 3600);
  const minutes = Math.floor((roundedSeconds % 3600) / 60);
  const seconds = Number((roundedSeconds % 60).toFixed(3));
  return { days, hours, minutes, seconds };
}

export function durationValue(
  parts,
  unit,
) {
  const totalSeconds = parts.days * 86400
    + parts.hours * 3600
    + parts.minutes * 60
    + parts.seconds;
  const rawValue = totalSeconds
    / (DURATION_UNIT_SECONDS[unit] || DURATION_UNIT_SECONDS.seconds);
  return String(Number(rawValue.toFixed(unit === "milliseconds" ? 3 : 6)));
}

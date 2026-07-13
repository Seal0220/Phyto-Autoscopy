export async function parseJsonResponse(response) {
  try {
    const payload = await response.json();
    return payload !== null && typeof payload === "object" ? payload : {};
  } catch {
    return {};
  }
}

export function responseErrorMessage(
  payload,
  fallback,
) {
  const detail = payload !== null && typeof payload === "object"
    ? payload.detail
    : null;
  if (typeof detail !== "string") return fallback;

  const normalized = detail.trim();
  if (
    !normalized
    || normalized.length > 500
    || /[\u0000-\u001f\u007f]/.test(normalized)
  ) {
    return fallback;
  }
  return normalized;
}

export function messageFromError(
  error,
  fallback,
) {
  return error instanceof Error
    && error.message
    && error.message !== "[object Object]"
    ? error.message
    : fallback;
}

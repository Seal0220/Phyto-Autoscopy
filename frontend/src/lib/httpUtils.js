export const DEFAULT_CLIENT_REQUEST_TIMEOUT_MS = 20_000;

export class RequestTimeoutError extends Error {
  constructor() {
    super("請求逾時。");
    this.name = "RequestTimeoutError";
  }
}

export async function withRequestTimeout(
  task,
  {
    signal,
    timeoutMs = DEFAULT_CLIENT_REQUEST_TIMEOUT_MS,
  } = {},
) {
  if (
    typeof task !== "function"
    || !Number.isFinite(timeoutMs)
    || timeoutMs <= 0
  ) {
    throw new TypeError("請求逾時設定無效。");
  }

  const controller = new AbortController();
  let abortCause = null;

  const abortFromCaller = () => {
    if (abortCause) return;
    abortCause = "caller";
    controller.abort(signal?.reason);
  };

  if (signal?.aborted) {
    abortFromCaller();
  } else {
    signal?.addEventListener("abort", abortFromCaller, { once: true });
  }

  const timeoutId = setTimeout(() => {
    if (abortCause) return;
    abortCause = "timeout";
    controller.abort();
  }, timeoutMs);

  try {
    const result = await task(controller.signal);

    if (abortCause === "timeout") {
      throw new RequestTimeoutError();
    }

    return result;
  } catch (error) {
    if (abortCause === "timeout") {
      throw new RequestTimeoutError();
    }

    throw error;
  } finally {
    clearTimeout(timeoutId);
    signal?.removeEventListener("abort", abortFromCaller);
  }
}

export async function parseJsonResponse(response) {
  try {
    const payload = await response.json();
    return payload !== null && typeof payload === "object" ? payload : {};
  } catch (error) {
    if (error?.name === "AbortError") throw error;
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

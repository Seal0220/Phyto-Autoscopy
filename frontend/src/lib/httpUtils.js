export const DEFAULT_CLIENT_REQUEST_TIMEOUT_MS = 20_000;

export class RequestTimeoutError extends Error {
  constructor() {
    super("請求逾時。");
    this.name = "RequestTimeoutError";
  }
}

export class UnknownMutationOutcomeError extends Error {
  constructor(message) {
    super(message);
    this.name = "UnknownMutationOutcomeError";
  }
}

export function abortRequest(
  controller,
  reason = "請求已取消。",
) {
  if (!controller || controller.signal.aborted) return false;

  const abortReason = reason instanceof Error
    ? reason
    : new DOMException(
      String(reason || "請求已取消。"),
      "AbortError",
    );
  controller.abort(abortReason);
  return true;
}

const UNKNOWN_MUTATION_RESPONSE_CODES = new Set([
  "BACKEND_TIMEOUT",
  "BACKEND_UNAVAILABLE",
  "BACKEND_INVALID_RESPONSE",
]);

export function mutationResponseOutcomeUnknown(
  response,
  payload,
) {
  return Number(response?.status) >= 500
    || UNKNOWN_MUTATION_RESPONSE_CODES.has(payload?.code);
}

export function mutationTransportOutcomeUnknown(error) {
  return error instanceof RequestTimeoutError
    || error instanceof TypeError;
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
    abortRequest(
      controller,
      signal?.reason,
    );
  };

  if (signal?.aborted) {
    abortFromCaller();
  } else {
    signal?.addEventListener("abort", abortFromCaller, { once: true });
  }

  const timeoutId = setTimeout(() => {
    if (abortCause) return;
    abortCause = "timeout";
    abortRequest(
      controller,
      "請求逾時。",
    );
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

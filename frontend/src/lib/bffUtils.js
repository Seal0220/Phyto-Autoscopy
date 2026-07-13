export const MAX_PROXY_REQUEST_BYTES = 1_000_000;
export const MAX_PROXY_ERROR_BYTES = 64_000;

const SAFE_RETRY_METHODS = new Set(["GET", "HEAD", "OPTIONS"]);
const SENSITIVE_DETAIL_PATTERN = /(?:traceback|stack\s+trace|phyto_autoscopy_(?:bff_token|session_secret|operator_password)|x-phyto-bff-token|[\\/])/i;
const CONTROL_CHARACTER_PATTERN = /[\u0000-\u001f\u007f]/;

export class BodyTooLargeError extends Error {
  constructor() {
    super("Body exceeds the configured byte limit.");
    this.name = "BodyTooLargeError";
  }
}

export class BodyReadTimeoutError extends Error {
  constructor() {
    super("Body read timed out.");
    this.name = "BodyReadTimeoutError";
  }
}

export class InvalidContentLengthError extends Error {
  constructor() {
    super("Content-Length is invalid.");
    this.name = "InvalidContentLengthError";
  }
}

export class InvalidBackendPathError extends Error {
  constructor() {
    super("Backend path contains an invalid segment.");
    this.name = "InvalidBackendPathError";
  }
}

function validateContentLength(
  value,
  maximumBytes,
) {
  if (value === null) return;

  const normalized = value.trim();
  if (!/^\d+$/.test(normalized)) {
    throw new InvalidContentLengthError();
  }

  if (BigInt(normalized) > BigInt(maximumBytes)) {
    throw new BodyTooLargeError();
  }
}

export async function readStreamWithLimit(
  stream,
  maximumBytes,
  timeoutMs,
) {
  if (!stream) return new Uint8Array();

  const reader = stream.getReader();
  const chunks = [];
  let totalBytes = 0;
  let timeoutId;
  let timedOut = false;

  const timeoutPromise = Number.isFinite(timeoutMs) && timeoutMs > 0
    ? new Promise((
      _,
      reject,
    ) => {
      timeoutId = setTimeout(() => {
        timedOut = true;
        reject(new BodyReadTimeoutError());
      }, timeoutMs);
    })
    : null;

  try {
    while (true) {
      const readPromise = reader.read();
      const { done, value } = timeoutPromise
        ? await Promise.race([readPromise, timeoutPromise])
        : await readPromise;

      if (done) break;

      const chunk = value instanceof Uint8Array ? value : new Uint8Array(value);
      totalBytes += chunk.byteLength;
      if (totalBytes > maximumBytes) {
        throw new BodyTooLargeError();
      }
      chunks.push(chunk);
    }
  } catch (error) {
    await reader.cancel().catch(() => undefined);
    throw error;
  } finally {
    if (timeoutId) clearTimeout(timeoutId);
    if (timedOut) await reader.cancel().catch(() => undefined);
    reader.releaseLock();
  }

  const body = new Uint8Array(totalBytes);
  let offset = 0;
  for (const chunk of chunks) {
    body.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return body;
}

export async function readRequestBody(
  request,
  {
    maximumBytes = MAX_PROXY_REQUEST_BYTES,
    timeoutMs = 5_000,
  } = {},
) {
  validateContentLength(request.headers.get("content-length"), maximumBytes);
  const body = await readStreamWithLimit(request.body, maximumBytes, timeoutMs);
  return body.byteLength ? body : undefined;
}

export function buildBackendPath(
  prefix,
  path = [],
) {
  if (
    typeof prefix !== "string"
    || !prefix.startsWith("/")
    || prefix.startsWith("//")
    || prefix.includes("?")
    || prefix.includes("#")
  ) {
    throw new InvalidBackendPathError();
  }

  const rawSegments = Array.isArray(path)
    ? path
    : String(path).split("/").filter(Boolean);
  const encodedSegments = rawSegments.map((segment) => {
    if (
      typeof segment !== "string"
      || !segment
      || segment === "."
      || segment === ".."
      || segment.includes("/")
      || segment.includes("\\")
      || CONTROL_CHARACTER_PATTERN.test(segment)
    ) {
      throw new InvalidBackendPathError();
    }
    return encodeURIComponent(segment);
  });

  const normalizedPrefix = prefix.replace(/\/+$/, "");
  return encodedSegments.length
    ? `${normalizedPrefix}/${encodedSegments.join("/")}`
    : normalizedPrefix;
}

export function isJsonContentType(contentType) {
  return typeof contentType === "string"
    && /^(?:application|text)\/(?:[a-z0-9.+-]*\+)?json(?:\s*;|$)/i.test(contentType.trim());
}

export function isRetrySafeMethod(method) {
  return SAFE_RETRY_METHODS.has(String(method || "").toUpperCase());
}

export function sanitizeBackendDetail(
  detail,
  fallback,
) {
  if (typeof detail !== "string") return fallback;

  const normalized = detail.trim();
  if (
    !normalized
    || normalized.length > 500
    || CONTROL_CHARACTER_PATTERN.test(normalized)
    || SENSITIVE_DETAIL_PATTERN.test(normalized)
  ) {
    return fallback;
  }
  return normalized;
}

export function safeRetryAfter(
  value,
  fallback = null,
) {
  if (typeof value !== "string") return fallback;

  const normalized = value.trim();
  if (/^\d{1,6}$/.test(normalized)) return normalized;
  if (normalized.length <= 96 && Number.isFinite(Date.parse(normalized))) {
    return normalized;
  }
  return fallback;
}

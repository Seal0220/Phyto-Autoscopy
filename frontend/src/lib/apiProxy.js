import { NextResponse } from "next/server";

import {
  BackendConfigurationError,
  BackendTimeoutError,
  fetchBackend,
} from "@/lib/backend";
import {
  BodyReadTimeoutError,
  BodyTooLargeError,
  InvalidBackendPathError,
  InvalidContentLengthError,
  MAX_PROXY_ERROR_BYTES,
  buildBackendPath,
  isJsonContentType,
  isRetrySafeMethod,
  readRequestBody,
  readStreamWithLimit,
  safeRetryAfter,
  sanitizeBackendDetail,
} from "@/lib/bffUtils";
import { getSession } from "@/lib/session";

const BODY_METHODS = new Set(["POST", "PUT", "PATCH", "DELETE"]);
const FORWARDED_REQUEST_HEADERS = ["accept", "content-type", "if-range", "range"];
const FORWARDED_SUCCESS_HEADERS = [
  "accept-ranges",
  "content-disposition",
  "content-length",
  "content-range",
  "content-type",
  "etag",
  "last-modified",
];

function jsonError(
  detail,
  {
    status,
    code,
    retryable = false,
    retryAfter,
  },
) {
  const headers = new Headers({ "Cache-Control": "no-store" });
  if (retryAfter) headers.set("Retry-After", retryAfter);
  return NextResponse.json(
    {
      detail,
      code,
      retryable,
    },
    {
      status,
      headers,
    },
  );
}

function unauthorizedResponse() {
  return jsonError("請先登入。", {
    status: 401,
    code: "SESSION_REQUIRED",
  });
}

function requestBodyError(error) {
  if (error instanceof BodyTooLargeError) {
    return jsonError("請求資料過大。", {
      status: 413,
      code: "REQUEST_TOO_LARGE",
    });
  }
  if (error instanceof InvalidContentLengthError) {
    return jsonError("請求資料長度格式錯誤。", {
      status: 400,
      code: "INVALID_CONTENT_LENGTH",
    });
  }
  if (error instanceof BodyReadTimeoutError) {
    return jsonError("讀取請求資料逾時。", {
      status: 408,
      code: "REQUEST_BODY_TIMEOUT",
    });
  }
  return jsonError("無法讀取請求資料。", {
    status: 400,
    code: "INVALID_REQUEST_BODY",
  });
}

function logTransportFailure(error) {
  const causeCode = typeof error?.cause?.code === "string"
    ? error.cause.code.slice(0, 64)
    : undefined;
  console.error("BFF backend transport failed", {
    type: error instanceof Error ? error.name : typeof error,
    causeCode,
  });
}

function transportErrorResponse(
  error,
  method,
) {
  const retryable = isRetrySafeMethod(method);
  logTransportFailure(error);

  if (error instanceof BackendConfigurationError) {
    return jsonError("後端服務暫時無法使用。", {
      status: 503,
      code: "BACKEND_CONFIGURATION_ERROR",
    });
  }
  if (error instanceof BackendTimeoutError) {
    const detail = retryable
      ? "後端服務回應逾時，請稍後再試。"
      : "後端服務回應逾時，操作結果尚未確認，請先重新整理狀態。";
    return jsonError(detail, {
      status: 504,
      code: "BACKEND_TIMEOUT",
      retryable,
      retryAfter: retryable ? "1" : undefined,
    });
  }
  const detail = retryable
    ? "後端服務暫時無法使用，請稍後再試。"
    : "與後端服務的連線中斷，操作結果尚未確認，請先重新整理狀態。";
  return jsonError(detail, {
    status: 502,
    code: "BACKEND_UNAVAILABLE",
    retryable,
    retryAfter: retryable ? "1" : undefined,
  });
}

function fallbackDetail(status) {
  if (status === 400) return "請求資料格式錯誤。";
  if (status === 403) return "目前的使用者角色沒有執行此操作的權限。";
  if (status === 404) return "找不到指定資源。";
  if (status === 405) return "此資源不支援目前的請求方法。";
  if (status === 408) return "後端服務處理請求逾時。";
  if (status === 413) return "請求資料過大。";
  if (status === 422) return "請求資料格式錯誤。";
  if (status === 429) return "操作過於頻繁，請稍後再試。";
  return "後端服務拒絕了這次請求。";
}

function errorCode(status) {
  if (status === 400) return "BACKEND_BAD_REQUEST";
  if (status === 403) return "FORBIDDEN";
  if (status === 404) return "NOT_FOUND";
  if (status === 405) return "METHOD_NOT_ALLOWED";
  if (status === 408) return "BACKEND_REQUEST_TIMEOUT";
  if (status === 413) return "REQUEST_TOO_LARGE";
  if (status === 422) return "VALIDATION_ERROR";
  if (status === 429) return "RATE_LIMITED";
  return "BACKEND_REJECTED";
}

async function backendErrorDetail(
  response,
  fallback,
) {
  if (!isJsonContentType(response.headers.get("content-type"))) {
    await response.body?.cancel().catch(() => undefined);
    return fallback;
  }

  try {
    const body = await readStreamWithLimit(
      response.body,
      MAX_PROXY_ERROR_BYTES,
      2_000,
    );
    if (!body.byteLength) return fallback;
    const payload = JSON.parse(new TextDecoder().decode(body));
    return sanitizeBackendDetail(payload?.detail, fallback);
  } catch {
    return fallback;
  }
}

function safeAllowHeader(value) {
  if (typeof value !== "string") return null;
  const normalized = value.trim().toUpperCase();
  return /^(?:GET|HEAD|POST|PUT|PATCH|DELETE|OPTIONS)(?:\s*,\s*(?:GET|HEAD|POST|PUT|PATCH|DELETE|OPTIONS))*$/.test(normalized)
    ? normalized
    : null;
}

async function backendErrorResponse(
  response,
  method,
) {
  const retryableMethod = isRetrySafeMethod(method);

  if (response.status === 401) {
    await response.body?.cancel().catch(() => undefined);
    return jsonError("後端服務暫時無法使用。", {
      status: 502,
      code: "BACKEND_AUTHENTICATION_ERROR",
    });
  }

  if (response.status < 400 || response.status >= 500) {
    await response.body?.cancel().catch(() => undefined);
    const retryable = retryableMethod;
    const retryAfter = retryable
      ? safeRetryAfter(response.headers.get("retry-after"), "1")
      : undefined;
    const detail = retryable
      ? "後端服務暫時無法使用，請稍後再試。"
      : "後端服務回應異常，操作結果尚未確認，請先重新整理狀態。";
    return jsonError(detail, {
      status: 502,
      code: "BACKEND_INVALID_RESPONSE",
      retryable,
      retryAfter,
    });
  }

  const fallback = fallbackDetail(response.status);
  const detail = await backendErrorDetail(response, fallback);
  const retryable = response.status === 429
    || (response.status === 408 && retryableMethod);
  const retryAfter = retryable
    ? safeRetryAfter(response.headers.get("retry-after"), response.status === 429 ? "60" : "1")
    : undefined;
  const headers = new Headers();
  const allow = response.status === 405
    ? safeAllowHeader(response.headers.get("allow"))
    : null;
  if (allow) headers.set("Allow", allow);

  const normalized = jsonError(detail, {
    status: response.status,
    code: errorCode(response.status),
    retryable,
    retryAfter,
  });
  for (const [header, value] of headers) normalized.headers.set(header, value);
  return normalized;
}

function successResponse(response) {
  const headers = new Headers();
  for (const header of FORWARDED_SUCCESS_HEADERS) {
    const value = response.headers.get(header);
    if (value) headers.set(header, value);
  }
  headers.set("Cache-Control", "no-store");
  return new NextResponse(response.body, {
    status: response.status,
    headers,
  });
}

export async function proxyToBackend(
  request,
  targetPath,
  {
    timeoutMs,
  } = {},
) {
  let session;
  try {
    session = await getSession();
  } catch (error) {
    return transportErrorResponse(new BackendConfigurationError(), request.method);
  }

  if (!session) return unauthorizedResponse();
  if (typeof targetPath !== "string") {
    return jsonError("請求路徑格式錯誤。", {
      status: 400,
      code: "INVALID_BACKEND_PATH",
    });
  }

  const inboundUrl = new URL(request.url);
  const headers = {};
  for (const header of FORWARDED_REQUEST_HEADERS) {
    const value = request.headers.get(header);
    if (value) headers[header] = value;
  }

  let body;
  if (BODY_METHODS.has(request.method)) {
    try {
      body = await readRequestBody(request);
    } catch (error) {
      return requestBodyError(error);
    }
  }

  try {
    const path = `${targetPath}${inboundUrl.search}`;
    const response = await fetchBackend(path, {
      session,
      method: request.method,
      body,
      headers,
      timeoutMs,
    });
    return response.ok
      ? successResponse(response)
      : backendErrorResponse(response, request.method);
  } catch (error) {
    return transportErrorResponse(error, request.method);
  }
}

export function backendPath(
  prefix,
  path = [],
) {
  try {
    return buildBackendPath(prefix, path);
  } catch (error) {
    if (error instanceof InvalidBackendPathError) return null;
    throw error;
  }
}

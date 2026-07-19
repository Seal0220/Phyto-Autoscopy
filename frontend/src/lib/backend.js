const DEFAULT_BACKEND_ORIGIN = "http://127.0.0.1:22222";
const DEFAULT_BACKEND_TIMEOUT_MS = 15_000;

export class BackendConfigurationError extends Error {
  constructor() {
    super("Backend transport is not configured correctly.");
    this.name = "BackendConfigurationError";
  }
}

export class BackendTimeoutError extends Error {
  constructor() {
    super("Backend request timed out.");
    this.name = "BackendTimeoutError";
  }
}

function backendOrigin() {
  try {
    const url = new URL(process.env.BACKEND_INTERNAL_URL || DEFAULT_BACKEND_ORIGIN);
    if (
      !["http:", "https:"].includes(url.protocol)
      || url.username
      || url.password
      || url.pathname !== "/"
      || url.search
      || url.hash
    ) {
      throw new BackendConfigurationError();
    }
    return url.origin;
  } catch (error) {
    if (error instanceof BackendConfigurationError) throw error;
    throw new BackendConfigurationError();
  }
}

function bffToken() {
  const token = process.env.PHYTO_AUTOSCOPY_BFF_TOKEN?.trim();
  if (!token) {
    throw new BackendConfigurationError();
  }
  return token;
}

export function backendUrl(path) {
  if (
    typeof path !== "string"
    || !path.startsWith("/")
    || path.startsWith("//")
    || /[\r\n]/.test(path)
  ) {
    throw new BackendConfigurationError();
  }
  return `${backendOrigin()}${path}`;
}

export async function fetchBackend(
  path,
  {
    session,
    method,
    body,
    headers = {},
    timeoutMs = DEFAULT_BACKEND_TIMEOUT_MS,
  },
) {
  if (
    !session
    || typeof session.actor !== "string"
    || typeof session.role !== "string"
    || !Number.isFinite(timeoutMs)
    || timeoutMs <= 0
  ) {
    throw new BackendConfigurationError();
  }

  const outboundHeaders = new Headers(headers);
  outboundHeaders.set("X-Phyto-BFF-Token", bffToken());
  outboundHeaders.set("X-Phyto-Actor", session.actor);
  outboundHeaders.set("X-Phyto-Role", session.role);

  const controller = new AbortController();
  let timedOut = false;
  const timeout = setTimeout(() => {
    timedOut = true;
    controller.abort(new DOMException(
      "後端請求逾時。",
      "AbortError",
    ));
  }, timeoutMs);

  try {
    return await fetch(backendUrl(path), {
      method,
      body,
      cache: "no-store",
      redirect: "manual",
      headers: outboundHeaders,
      signal: controller.signal,
    });
  } catch (error) {
    if (timedOut) throw new BackendTimeoutError();
    throw error;
  } finally {
    clearTimeout(timeout);
  }
}

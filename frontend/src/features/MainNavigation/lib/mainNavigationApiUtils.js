import {
  parseJsonResponse,
  responseErrorMessage,
  withRequestTimeout,
} from "@/lib/httpUtils";

const MAIN_NAVIGATION_ACTION_TIMEOUT_MS = 20_000;

export async function postMainNavigationAction(
  endpoint,
  fallback,
  signal,
) {
  const response = await withRequestTimeout(
    (requestSignal) => fetch(endpoint, {
      method: "POST",
      signal: requestSignal,
    }),
    {
      signal,
      timeoutMs: MAIN_NAVIGATION_ACTION_TIMEOUT_MS,
    },
  );
  const payload = await parseJsonResponse(response);

  if (!response.ok) {
    throw new Error(responseErrorMessage(
      payload,
      fallback,
    ));
  }

  return payload;
}

export function parseJsonResponse(response) {
  return response.json().catch(() => ({}));
}

export function messageFromError(error, fallback) {
  return error instanceof Error && error.message ? error.message : fallback;
}

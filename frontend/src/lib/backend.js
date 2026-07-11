function backendOrigin() {
  return (process.env.BACKEND_INTERNAL_URL || "http://127.0.0.1:22222").replace(/\/$/, "");
}

function bffToken() {
  const token = process.env.PHYTO_AUTOSCOPY_BFF_TOKEN;
  if (!token) {
    throw new Error("PHYTO_AUTOSCOPY_BFF_TOKEN is not configured.");
  }
  return token;
}

export function backendUrl(path) {
  return `${backendOrigin()}${path.startsWith("/") ? path : `/${path}`}`;
}

export async function fetchBackend(path, { session, method, body, headers = {} }) {
  return fetch(backendUrl(path), {
    method,
    body,
    cache: "no-store",
    redirect: "manual",
    headers: {
      "X-Phyto-BFF-Token": bffToken(),
      "X-Phyto-Actor": session.actor,
      "X-Phyto-Role": session.role,
      ...headers,
    },
  });
}

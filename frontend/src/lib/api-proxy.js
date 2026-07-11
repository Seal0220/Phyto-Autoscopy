import { NextResponse } from "next/server";

import { fetchBackend } from "@/lib/backend";
import { getSession } from "@/lib/session";

const BODY_METHODS = new Set(["POST", "PUT", "PATCH", "DELETE"]);
const FORWARDED_REQUEST_HEADERS = ["accept", "content-type"];
const FORWARDED_RESPONSE_HEADERS = ["content-type", "content-disposition", "cache-control"];

function unauthorizedResponse() {
  return NextResponse.json({ detail: "Authentication required." }, { status: 401 });
}

function errorResponse(error) {
  console.error("BFF request failed", error);
  return NextResponse.json({ detail: "Backend service is unavailable." }, { status: 502 });
}

function safeBackendPath(path) {
  return path
    .split("/")
    .filter(Boolean)
    .map((segment) => encodeURIComponent(segment))
    .join("/");
}

export async function proxyToBackend(request, backendPath) {
  const session = await getSession();
  if (!session) {
    return unauthorizedResponse();
  }

  const inboundUrl = new URL(request.url);
  const headers = {};
  for (const header of FORWARDED_REQUEST_HEADERS) {
    const value = request.headers.get(header);
    if (value) {
      headers[header] = value;
    }
  }

  let body;
  if (BODY_METHODS.has(request.method)) {
    body = await request.arrayBuffer();
    if (body.byteLength > 1_000_000) {
      return NextResponse.json({ detail: "Request body is too large." }, { status: 413 });
    }
  }

  try {
    const path = `${backendPath}${inboundUrl.search}`;
    const backendResponse = await fetchBackend(path, {
      session,
      method: request.method,
      body,
      headers,
    });
    const responseHeaders = new Headers();
    for (const header of FORWARDED_RESPONSE_HEADERS) {
      const value = backendResponse.headers.get(header);
      if (value) {
        responseHeaders.set(header, value);
      }
    }
    responseHeaders.set("Cache-Control", "no-store");
    return new NextResponse(backendResponse.body, {
      status: backendResponse.status,
      headers: responseHeaders,
    });
  } catch (error) {
    return errorResponse(error);
  }
}

export function backendPath(prefix, path = []) {
  const suffix = safeBackendPath(Array.isArray(path) ? path.join("/") : path);
  return suffix ? `${prefix}/${suffix}` : prefix;
}

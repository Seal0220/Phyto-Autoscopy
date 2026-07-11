import crypto from "node:crypto";

import { cookies } from "next/headers";

export const SESSION_COOKIE_NAME = "phyto_autoscopy_session";
const SESSION_TTL_SECONDS = 60 * 60 * 12;

function sessionSecret() {
  const value = process.env.PHYTO_AUTOSCOPY_SESSION_SECRET;
  if (!value) {
    throw new Error("PHYTO_AUTOSCOPY_SESSION_SECRET is not configured.");
  }
  return value;
}

function base64Url(value) {
  return Buffer.from(value).toString("base64url");
}

function sign(payload) {
  return crypto.createHmac("sha256", sessionSecret()).update(payload).digest("base64url");
}

function verifySignature(payload, signature) {
  const expected = Buffer.from(sign(payload));
  const supplied = Buffer.from(signature || "");
  return expected.length === supplied.length && crypto.timingSafeEqual(expected, supplied);
}

function encodeSession(session) {
  const payload = base64Url(JSON.stringify(session));
  return `${payload}.${sign(payload)}`;
}

function decodeSession(token) {
  if (!token || !token.includes(".")) {
    return null;
  }
  const [payload, signature] = token.split(".", 2);
  if (!verifySignature(payload, signature)) {
    return null;
  }
  try {
    const session = JSON.parse(Buffer.from(payload, "base64url").toString("utf8"));
    if (
      !session ||
      typeof session.actor !== "string" ||
      typeof session.role !== "string" ||
      !Number.isFinite(session.expiresAt) ||
      session.expiresAt <= Date.now()
    ) {
      return null;
    }
    return session;
  } catch {
    return null;
  }
}

export async function getSession() {
  const store = await cookies();
  return decodeSession(store.get(SESSION_COOKIE_NAME)?.value);
}

export async function createOperatorSession() {
  const session = {
    actor: "operator",
    role: "operator",
    expiresAt: Date.now() + SESSION_TTL_SECONDS * 1000,
  };
  const store = await cookies();
  store.set(SESSION_COOKIE_NAME, encodeSession(session), {
    httpOnly: true,
    sameSite: "strict",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: SESSION_TTL_SECONDS,
  });
  return session;
}

export async function clearSession() {
  const store = await cookies();
  store.set(SESSION_COOKIE_NAME, "", {
    httpOnly: true,
    sameSite: "strict",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: 0,
  });
}

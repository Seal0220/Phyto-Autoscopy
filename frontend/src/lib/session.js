import { cookies } from "next/headers";

import {
  decodeSessionToken,
  encodeSessionToken,
} from "@/lib/sessionToken";

export const SESSION_COOKIE_NAME = "phyto_autoscopy_session";
const SESSION_TTL_SECONDS = 60 * 60 * 24 * 7;

function sessionSecret() {
  const value = process.env.PHYTO_AUTOSCOPY_SESSION_SECRET;
  if (!value) {
    throw new Error("PHYTO_AUTOSCOPY_SESSION_SECRET is not configured.");
  }
  return value;
}

export async function getSession() {
  const store = await cookies();
  const token = store.get(SESSION_COOKIE_NAME)?.value;
  if (!token) return null;

  const secret = process.env.PHYTO_AUTOSCOPY_SESSION_SECRET;
  if (!secret) return null;
  return decodeSessionToken(
    token,
    secret,
  );
}

export async function createOperatorSession() {
  return writeSession({
    actor: "operator",
    role: "operator",
  });
}

export async function renewSession(session) {
  if (!session) return null;

  return writeSession({
    actor: session.actor,
    role: session.role,
  });
}

async function writeSession({
  actor,
  role,
}) {
  const session = {
    actor,
    role,
    expiresAt: Date.now() + SESSION_TTL_SECONDS * 1000,
  };
  const store = await cookies();
  store.set(SESSION_COOKIE_NAME, encodeSessionToken(session, sessionSecret()), {
    httpOnly: true,
    sameSite: "strict",
    secure: false,
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
    secure: false,
    path: "/",
    maxAge: 0,
  });
}

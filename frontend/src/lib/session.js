import { cookies } from "next/headers";

import {
  decodeSessionToken,
  encodeSessionToken,
} from "@/lib/sessionToken";

export const SESSION_COOKIE_NAME = "phyto_autoscopy_session";
const SESSION_TTL_SECONDS = 60 * 60 * 12;

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
  const session = {
    actor: "operator",
    role: "operator",
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

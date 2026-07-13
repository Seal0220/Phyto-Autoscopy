import crypto from "node:crypto";

const ACTOR_PATTERN = /^[A-Za-z0-9_.@:-]{1,96}$/;
const SESSION_ROLES = new Set(["viewer", "operator", "admin"]);

function signatureFor(
  payload,
  secret,
) {
  return crypto.createHmac("sha256", secret).update(payload).digest("base64url");
}

function signaturesMatch(
  payload,
  signature,
  secret,
) {
  const expected = Buffer.from(signatureFor(payload, secret));
  const supplied = Buffer.from(signature || "");
  return expected.length === supplied.length && crypto.timingSafeEqual(expected, supplied);
}

export function encodeSessionToken(
  session,
  secret,
) {
  const payload = Buffer.from(JSON.stringify(session)).toString("base64url");
  return `${payload}.${signatureFor(payload, secret)}`;
}

export function decodeSessionToken(
  token,
  secret,
  now = Date.now(),
) {
  if (typeof token !== "string") return null;

  const parts = token.split(".");
  if (parts.length !== 2) return null;

  const [payload, signature] = parts;
  if (!payload || !signaturesMatch(payload, signature, secret)) return null;

  try {
    const session = JSON.parse(Buffer.from(payload, "base64url").toString("utf8"));
    if (
      !session
      || typeof session.actor !== "string"
      || !ACTOR_PATTERN.test(session.actor)
      || typeof session.role !== "string"
      || !SESSION_ROLES.has(session.role)
      || !Number.isFinite(session.expiresAt)
      || session.expiresAt <= now
    ) {
      return null;
    }
    return session;
  } catch {
    return null;
  }
}

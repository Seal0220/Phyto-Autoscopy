import assert from "node:assert/strict";
import test from "node:test";

import { passwordsMatch } from "../src/lib/authUtils.js";
import {
  decodeSessionToken,
  encodeSessionToken,
} from "../src/lib/sessionToken.js";

test("password comparison uses fixed-length digests", () => {
  assert.equal(passwordsMatch("correct horse", "correct horse"), true);
  assert.equal(passwordsMatch("short", "a much longer password"), false);
  assert.equal(passwordsMatch("", "configured"), false);
});

test("session tokens require an exact signed two-part format", () => {
  const secret = "test-session-secret";
  const now = 1_000_000;
  const session = {
    actor: "operator",
    role: "operator",
    expiresAt: now + 60_000,
  };
  const token = encodeSessionToken(session, secret);

  assert.equal(decodeSessionToken(undefined, undefined, now), null);
  assert.deepEqual(decodeSessionToken(token, secret, now), session);
  assert.equal(decodeSessionToken(`${token}.extra`, secret, now), null);
  assert.equal(decodeSessionToken(`${token.slice(0, -1)}x`, secret, now), null);
  assert.equal(decodeSessionToken(token, "wrong-secret", now), null);
  assert.equal(decodeSessionToken(token, secret, session.expiresAt), null);
});

test("session tokens reject actors and roles the backend would reject", () => {
  const secret = "test-session-secret";
  const now = 1_000_000;
  const invalidActor = encodeSessionToken({
    actor: "bad actor",
    role: "operator",
    expiresAt: now + 60_000,
  }, secret);
  const invalidRole = encodeSessionToken({
    actor: "operator",
    role: "unknown",
    expiresAt: now + 60_000,
  }, secret);

  assert.equal(decodeSessionToken(invalidActor, secret, now), null);
  assert.equal(decodeSessionToken(invalidRole, secret, now), null);
});

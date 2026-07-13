import assert from "node:assert/strict";
import {
  afterEach,
  test,
} from "node:test";

import {
  BackendConfigurationError,
  BackendTimeoutError,
  backendUrl,
  fetchBackend,
} from "../src/lib/backend.js";

const originalFetch = globalThis.fetch;
const originalBackendUrl = process.env.BACKEND_INTERNAL_URL;
const originalBffToken = process.env.PHYTO_AUTOSCOPY_BFF_TOKEN;

afterEach(() => {
  globalThis.fetch = originalFetch;
  if (originalBackendUrl === undefined) delete process.env.BACKEND_INTERNAL_URL;
  else process.env.BACKEND_INTERNAL_URL = originalBackendUrl;
  if (originalBffToken === undefined) delete process.env.PHYTO_AUTOSCOPY_BFF_TOKEN;
  else process.env.PHYTO_AUTOSCOPY_BFF_TOKEN = originalBffToken;
});

test("fetchBackend applies trusted identity headers after caller headers", async () => {
  process.env.BACKEND_INTERNAL_URL = "http://127.0.0.1:22222";
  process.env.PHYTO_AUTOSCOPY_BFF_TOKEN = " trusted-token ";
  let captured;
  globalThis.fetch = async (url, options) => {
    captured = { url, options };
    return new Response("{}", {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  };

  await fetchBackend("/api/system/status", {
    session: { actor: "operator", role: "operator" },
    method: "GET",
    headers: {
      Accept: "application/json",
      "X-Phyto-BFF-Token": "untrusted-token",
    },
    timeoutMs: 100,
  });

  assert.equal(captured.url, "http://127.0.0.1:22222/api/system/status");
  assert.equal(captured.options.cache, "no-store");
  assert.equal(captured.options.redirect, "manual");
  assert.equal(captured.options.headers.get("X-Phyto-BFF-Token"), "trusted-token");
  assert.equal(captured.options.headers.get("X-Phyto-Actor"), "operator");
  assert.equal(captured.options.headers.get("X-Phyto-Role"), "operator");
});

test("fetchBackend rejects missing credentials and invalid origins safely", async () => {
  delete process.env.PHYTO_AUTOSCOPY_BFF_TOKEN;
  await assert.rejects(
    fetchBackend("/api/system/status", {
      session: { actor: "operator", role: "operator" },
      method: "GET",
      timeoutMs: 100,
    }),
    BackendConfigurationError,
  );

  process.env.BACKEND_INTERNAL_URL = "http://user:password@127.0.0.1:22222";
  assert.throws(() => backendUrl("/api/system/status"), BackendConfigurationError);
  process.env.BACKEND_INTERNAL_URL = "http://127.0.0.1:22222/base";
  assert.throws(() => backendUrl("/api/system/status"), BackendConfigurationError);
  process.env.BACKEND_INTERNAL_URL = "http://127.0.0.1:22222";
  assert.throws(() => backendUrl("//outside.example/api"), BackendConfigurationError);
});

test("fetchBackend reports a distinct timeout without exposing fetch errors", async () => {
  process.env.BACKEND_INTERNAL_URL = "http://127.0.0.1:22222";
  process.env.PHYTO_AUTOSCOPY_BFF_TOKEN = "trusted-token";
  globalThis.fetch = async (_url, { signal }) => new Promise((resolve, reject) => {
    signal.addEventListener(
      "abort",
      () => reject(new DOMException("aborted", "AbortError")),
      { once: true },
    );
  });

  await assert.rejects(
    fetchBackend("/api/system/status", {
      session: { actor: "operator", role: "operator" },
      method: "GET",
      timeoutMs: 5,
    }),
    BackendTimeoutError,
  );
});

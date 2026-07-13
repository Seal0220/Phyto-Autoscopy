import assert from "node:assert/strict";
import test from "node:test";

import {
  BodyReadTimeoutError,
  BodyTooLargeError,
  InvalidBackendPathError,
  InvalidContentLengthError,
  buildBackendPath,
  isJsonContentType,
  isRetrySafeMethod,
  readRequestBody,
  safeRetryAfter,
  sanitizeBackendDetail,
} from "../src/lib/bffUtils.js";

test("buildBackendPath encodes identifiers without changing route depth", () => {
  assert.equal(
    buildBackendPath("/api/records", ["record one", "metadata"]),
    "/api/records/record%20one/metadata",
  );
});

test("buildBackendPath rejects traversal and decoded separator segments", () => {
  for (const segment of [".", "..", "nested/path", "nested\\path", "bad\u0000path"]) {
    assert.throws(
      () => buildBackendPath("/api/records", [segment]),
      InvalidBackendPathError,
    );
  }
});

test("readRequestBody enforces declared and streamed byte limits", async () => {
  const valid = new Request("http://local.test/api", {
    method: "POST",
    headers: { "Content-Length": "4" },
    body: "test",
  });
  assert.deepEqual(
    [...await readRequestBody(valid, { maximumBytes: 4, timeoutMs: 100 })],
    [116, 101, 115, 116],
  );

  const declaredTooLarge = new Request("http://local.test/api", {
    method: "POST",
    headers: { "Content-Length": "5" },
    body: "test",
  });
  await assert.rejects(
    readRequestBody(declaredTooLarge, { maximumBytes: 4, timeoutMs: 100 }),
    BodyTooLargeError,
  );

  const invalidLength = new Request("http://local.test/api", {
    method: "POST",
    headers: { "Content-Length": "4x" },
    body: "test",
  });
  await assert.rejects(
    readRequestBody(invalidLength, { maximumBytes: 4, timeoutMs: 100 }),
    InvalidContentLengthError,
  );

  const streamedTooLarge = new Request("http://local.test/api", {
    method: "POST",
    body: new ReadableStream({
      start(controller) {
        controller.enqueue(new Uint8Array([1, 2, 3, 4, 5]));
        controller.close();
      },
    }),
    duplex: "half",
  });
  await assert.rejects(
    readRequestBody(streamedTooLarge, { maximumBytes: 4, timeoutMs: 100 }),
    BodyTooLargeError,
  );
});

test("readRequestBody times out stalled request streams", async () => {
  const stalled = new Request("http://local.test/api", {
    method: "POST",
    body: new ReadableStream({ start() {} }),
    duplex: "half",
  });
  await assert.rejects(
    readRequestBody(stalled, { maximumBytes: 4, timeoutMs: 5 }),
    BodyReadTimeoutError,
  );
});

test("backend error helpers preserve only bounded safe string details", () => {
  const fallback = "請求失敗。";
  assert.equal(sanitizeBackendDetail("馬達尚未啟用。", fallback), "馬達尚未啟用。");
  assert.equal(sanitizeBackendDetail([{ msg: "invalid" }], fallback), fallback);
  assert.equal(sanitizeBackendDetail("找不到設定檔：C:\\private\\config.json", fallback), fallback);
  assert.equal(sanitizeBackendDetail("找不到設定檔：config/default.json", fallback), fallback);
  assert.equal(sanitizeBackendDetail("PHYTO_AUTOSCOPY_BFF_TOKEN missing", fallback), fallback);
  assert.equal(isJsonContentType("application/problem+json; charset=utf-8"), true);
  assert.equal(isJsonContentType("text/html"), false);
  assert.equal(isRetrySafeMethod("GET"), true);
  assert.equal(isRetrySafeMethod("POST"), false);
  assert.equal(safeRetryAfter("60"), "60");
  assert.equal(safeRetryAfter("bad\r\nvalue", null), null);
});

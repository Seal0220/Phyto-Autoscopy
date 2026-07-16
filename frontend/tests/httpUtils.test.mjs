import assert from "node:assert/strict";
import test from "node:test";

import {
  RequestTimeoutError,
  messageFromError,
  parseJsonResponse,
  responseErrorMessage,
  withRequestTimeout,
} from "../src/lib/httpUtils.js";

function waitUntilAborted(signal) {
  return new Promise((resolve, reject) => {
    const rejectWithReason = () => reject(signal.reason);

    if (signal.aborted) {
      rejectWithReason();
      return;
    }

    signal.addEventListener("abort", rejectWithReason, { once: true });
  });
}

test("parseJsonResponse accepts collections and normalizes invalid bodies", async () => {
  assert.deepEqual(
    await parseJsonResponse(new Response('[{"id":1}]')),
    [{ id: 1 }],
  );
  assert.deepEqual(await parseJsonResponse(new Response("not-json")), {});
  assert.deepEqual(await parseJsonResponse(new Response("null")), {});
  assert.deepEqual(await parseJsonResponse(new Response("42")), {});
});

test("parseJsonResponse preserves request cancellation", async () => {
  await assert.rejects(
    parseJsonResponse({
      json: async () => {
        throw new DOMException("已取消", "AbortError");
      },
    }),
    (error) => error?.name === "AbortError",
  );
});

test("responseErrorMessage never converts structured details to object text", () => {
  const fallback = "操作失敗。";
  assert.equal(responseErrorMessage({ detail: "請求資料錯誤。" }, fallback), "請求資料錯誤。");
  assert.equal(responseErrorMessage({ detail: [{ msg: "invalid" }] }, fallback), fallback);
  assert.equal(responseErrorMessage({}, fallback), fallback);
  assert.equal(responseErrorMessage(null, fallback), fallback);
  assert.equal(messageFromError(new Error("[object Object]"), fallback), fallback);
});

test("withRequestTimeout ends a request whose response body never completes", async () => {
  await assert.rejects(
    withRequestTimeout(
      waitUntilAborted,
      {
        timeoutMs: 5,
      },
    ),
    RequestTimeoutError,
  );
});

test("withRequestTimeout preserves caller cancellation", async () => {
  const controller = new AbortController();
  const request = withRequestTimeout(
    waitUntilAborted,
    {
      signal: controller.signal,
      timeoutMs: 1_000,
    },
  );

  controller.abort();

  await assert.rejects(
    request,
    (error) => error?.name === "AbortError",
  );
});

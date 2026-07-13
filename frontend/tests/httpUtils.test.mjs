import assert from "node:assert/strict";
import test from "node:test";

import {
  messageFromError,
  parseJsonResponse,
  responseErrorMessage,
} from "../src/lib/httpUtils.js";

test("parseJsonResponse accepts collections and normalizes invalid bodies", async () => {
  assert.deepEqual(
    await parseJsonResponse(new Response('[{"id":1}]')),
    [{ id: 1 }],
  );
  assert.deepEqual(await parseJsonResponse(new Response("not-json")), {});
  assert.deepEqual(await parseJsonResponse(new Response("null")), {});
  assert.deepEqual(await parseJsonResponse(new Response("42")), {});
});

test("responseErrorMessage never converts structured details to object text", () => {
  const fallback = "操作失敗。";
  assert.equal(responseErrorMessage({ detail: "請求資料錯誤。" }, fallback), "請求資料錯誤。");
  assert.equal(responseErrorMessage({ detail: [{ msg: "invalid" }] }, fallback), fallback);
  assert.equal(responseErrorMessage({}, fallback), fallback);
  assert.equal(responseErrorMessage(null, fallback), fallback);
  assert.equal(messageFromError(new Error("[object Object]"), fallback), fallback);
});

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import test from "node:test";
import vm from "node:vm";

import * as bffUtils from "../src/lib/bffUtils.js";

const require = createRequire(import.meta.url);
const swc = require("next/dist/build/swc");
await swc.loadBindings();
const filename = new URL("../src/lib/apiProxy.js", import.meta.url);
const { code } = swc.transformSync(readFileSync(filename, "utf8"), {
  filename: filename.pathname,
  jsc: { parser: { syntax: "ecmascript" } },
  module: { type: "commonjs" },
});

async function proxyRejection(detail, status = 400) {
  const compiledModule = { exports: {} };
  const calls = [];
  function resolve(name) {
    if (name === "@/lib/bffUtils") return bffUtils;
    if (name === "@/lib/session") return { getSession: async () => ({ username: "test" }) };
    if (name === "@/lib/backend") return {
      fetchBackend: async (path, options) => {
        calls.push({ path, options });
        return Response.json({ detail }, { status });
      },
    };
    return require(name);
  }
  vm.runInThisContext(`(function(require,module,exports){${code}\n})`)(resolve, compiledModule, compiledModule.exports);
  const request = new Request("http://local.test/api/analysis/test/stereo-review", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: "{}",
  });
  const response = await compiledModule.exports.proxyToBackend(request, "/api/analysis/test/stereo-review");
  assert.equal(calls.length, 1);
  assert.equal(response.status, status);
  assert.equal(response.headers.get("Cache-Control"), "no-store");
  return response.json();
}

test("manual alignment HTTP errors expose actionable counts and never retry the mutation", async () => {
  const reason = "俯視角：模型對齊未通過幾何檢查：有效參照點 3/5 組，至少需要四組。請優先檢查第 4、5 組。";
  assert.deepEqual(await proxyRejection(reason), {
    detail: reason.replace("3/5", "3／5"), code: "BACKEND_BAD_REQUEST", retryable: false,
  });
});

test("HTTP 400 is an operation rejection while actual schema failures remain HTTP 422", async () => {
  assert.equal((await proxyRejection("Traceback in C:\\private\\server.py")).detail, "這次操作未通過檢查，請確認輸入內容。");
  const schema = await proxyRejection([{ msg: "missing field", input: "private" }], 422);
  assert.equal(schema.detail, "請求資料格式錯誤。");
  assert.equal(schema.code, "VALIDATION_ERROR");
});

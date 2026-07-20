import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const settingsSource = readFileSync(
  new URL(
    "../src/features/ImagePreview/components/ImagePreviewSettings.js",
    import.meta.url,
  ),
  "utf8",
);

test("image preview reports simulated sources through global notifications", () => {
  assert.match(settingsSource, /onNotify\?\.\(/);
  assert.match(settingsSource, /目前使用模擬相機來源/);
  assert.doesNotMatch(settingsSource, /不會搜尋實體攝影機/);
  assert.doesNotMatch(settingsSource, /bg-amber-300\/10/);
});

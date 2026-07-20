import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";


const calibrationSource = await readFile(
  new URL("../src/features/Calibration/Calibration.js", import.meta.url),
  "utf8",
);
const boardSource = await readFile(
  new URL(
    "../src/features/Calibration/components/CalibrationBoardSettings.js",
    import.meta.url,
  ),
  "utf8",
);


test("校正頁由校正板、內部參數與外部參數三個頂層區塊組成", () => {
  assert.match(calibrationSource, /<Panel aria-label="校正板">/);
  assert.match(calibrationSource, /<Panel aria-label="內部參數">/);
  assert.match(calibrationSource, /<Panel aria-label="外部參數">/);
  assert.doesNotMatch(calibrationSource, /三相機即時預覽|各相機內參/);
});


test("校正板直接提供生成、預覽與下載，不保留新增切換", () => {
  assert.match(boardSource, />\s*生成校正板\s*</);
  assert.match(boardSource, />\s*下載校正板\s*</);
  assert.match(boardSource, /\/api\/calibration\/boards\/\$\{/);
  assert.match(boardSource, /label="紙張尺寸"/);
  assert.match(boardSource, /label="列印方向"/);
  assert.doesNotMatch(
    boardSource,
    /新增校正板|取消新增|使用的校正板|校正板名稱|校正板類型|ArUco Dictionary/,
  );
});

import assert from "node:assert/strict";
import {
  existsSync,
  readdirSync,
} from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const frontendRoot = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "..",
);
const appRoot = path.join(frontendRoot, "src", "app");
const pagesRoot = path.join(appRoot, "(pages)");

function pageFiles(directory) {
  return readdirSync(directory, {
    withFileTypes: true,
  }).flatMap((entry) => {
    const entryPath = path.join(directory, entry.name);
    if (entry.isDirectory()) {
      return pageFiles(entryPath);
    }
    return entry.name === "page.js" ? [entryPath] : [];
  });
}

test("all App Router page entries live below the pages route group", () => {
  const pages = pageFiles(appRoot);

  assert.ok(pages.length >= 5);
  assert.ok(pages.every((page) => page.startsWith(`${pagesRoot}${path.sep}`)));
  assert.equal(existsSync(path.join(appRoot, "(page)")), false);
});

test("the pages route group owns root, capture, analysis, and models entries", () => {
  const expected = [
    path.join(pagesRoot, "page.js"),
    path.join(pagesRoot, "capture", "page.js"),
    path.join(pagesRoot, "analysis", "page.js"),
    path.join(pagesRoot, "analysis", "new", "page.js"),
    path.join(pagesRoot, "analysis", "[analysisId]", "page.js"),
    path.join(pagesRoot, "analysis", "[analysisId]", "review", "page.js"),
    path.join(pagesRoot, "analysis", "[analysisId]", "results", "page.js"),
    path.join(pagesRoot, "models", "page.js"),
  ];

  for (const page of expected) {
    assert.equal(
      existsSync(page),
      true,
      page,
    );
  }
  assert.equal(existsSync(path.join(appRoot, "page.js")), false);
  assert.equal(existsSync(path.join(appRoot, "analysis", "page.js")), false);
  assert.equal(existsSync(path.join(appRoot, "capture", "page.js")), false);
  assert.equal(existsSync(path.join(appRoot, "models", "page.js")), false);
});

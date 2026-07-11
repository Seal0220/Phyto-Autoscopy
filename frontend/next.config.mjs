import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

function loadSharedServerEnvironment() {
  const frontendDir = path.dirname(fileURLToPath(import.meta.url));
  const envPath = path.resolve(frontendDir, "..", ".env");
  if (!fs.existsSync(envPath)) {
    return;
  }

  for (const rawLine of fs.readFileSync(envPath, "utf8").split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line || line.startsWith("#") || !line.includes("=")) {
      continue;
    }
    const separator = line.indexOf("=");
    const key = line.slice(0, separator).trim();
    let value = line.slice(separator + 1).trim();
    if (
      value.length >= 2 &&
      ((value.startsWith('"') && value.endsWith('"')) ||
        (value.startsWith("'") && value.endsWith("'")))
    ) {
      value = value.slice(1, -1);
    }
    if (key && process.env[key] === undefined) {
      process.env[key] = value;
    }
  }
}

// Root .env contains shared private settings. This runs only in the Next.js
// server process and never makes those values available to browser bundles.
loadSharedServerEnvironment();

const backendOrigin = (process.env.BACKEND_INTERNAL_URL || "http://127.0.0.1:22222").replace(
  /\/$/,
  "",
);

/** @type {import('next').NextConfig} */
const nextConfig = {
  async rewrites() {
    return [
      // The browser reaches only the Next.js origin. This rewrite upgrades the
      // same-origin WebSocket path to the backend's loopback-only socket.
      {
        source: "/ws/status",
        destination: `${backendOrigin}/ws/status`,
      },
    ];
  },
};

export default nextConfig;

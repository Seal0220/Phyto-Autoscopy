import { proxyToBackend } from "@/lib/apiProxy";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

async function handler(request) {
  return proxyToBackend(
    request,
    "/api/calibration",
    {
      timeoutMs: request.method === "GET"
        ? 20_000
        : 60_000,
    },
  );
}

export {
  handler as DELETE,
  handler as GET,
  handler as PATCH,
  handler as POST,
};

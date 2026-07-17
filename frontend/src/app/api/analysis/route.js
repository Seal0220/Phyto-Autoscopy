import { proxyToBackend } from "@/lib/apiProxy";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

async function handler(request) {
  return proxyToBackend(
    request,
    "/api/analysis",
    {
      timeoutMs: request.method === "POST"
        ? 120_000
        : 60_000,
    },
  );
}

export {
  handler as GET,
  handler as POST,
};

import { backendPath, proxyToBackend } from "@/lib/api-proxy";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

async function handler(request, context) {
  const { path = [] } = await context.params;
  return proxyToBackend(request, backendPath("/api/experiments", path));
}

export { handler as GET, handler as POST };

import { backendPath, proxyToBackend } from "@/lib/apiProxy";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

async function handler(request, context) {
  const { path = [] } = await context.params;
  return proxyToBackend(request, backendPath("/api/cameras", path));
}

export { handler as DELETE, handler as GET, handler as PATCH, handler as POST, handler as PUT };

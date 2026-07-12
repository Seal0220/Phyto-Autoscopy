import { proxyToBackend } from "@/lib/apiProxy";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

async function handler(request) {
  return proxyToBackend(request, "/api/motor");
}

export { handler as GET, handler as POST };

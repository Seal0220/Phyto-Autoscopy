import { proxyToBackend } from "@/lib/apiProxy";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

async function handler(request) {
  return proxyToBackend(request, "/api/sessions");
}

export { handler as DELETE, handler as GET, handler as POST };

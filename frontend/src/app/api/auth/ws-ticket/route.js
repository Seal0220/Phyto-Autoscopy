import { proxyToBackend } from "@/lib/api-proxy";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(request) {
  return proxyToBackend(request, "/api/auth/ws-ticket");
}

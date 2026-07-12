import { proxyToBackend } from "@/lib/apiProxy";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(request) {
  return proxyToBackend(request, "/api/auth/ws-ticket");
}

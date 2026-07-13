import { backendPath, proxyToBackend } from "@/lib/apiProxy";
import { cameraProxyTimeout } from "@/lib/proxyTimeoutUtils";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

async function handler(
  request,
  context,
) {
  const { path = [] } = await context.params;
  return proxyToBackend(
    request,
    backendPath("/api/cameras", path),
    {
      timeoutMs: cameraProxyTimeout(path),
    },
  );
}

export { handler as GET, handler as POST };

import { backendPath, proxyToBackend } from "@/lib/apiProxy";
import { motorProxyTimeout } from "@/lib/proxyTimeoutUtils";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

async function handler(
  request,
  context,
) {
  const { path = [] } = await context.params;
  return proxyToBackend(
    request,
    backendPath("/api/motor", path),
    {
      timeoutMs: motorProxyTimeout(path),
    },
  );
}

export { handler as GET, handler as POST };

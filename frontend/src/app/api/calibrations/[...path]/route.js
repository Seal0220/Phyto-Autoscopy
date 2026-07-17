import {
  backendPath,
  proxyToBackend,
} from "@/lib/apiProxy";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

function calibrationProxyTimeout(
  method,
  path,
) {
  if (method === "POST") return 120_000;
  if (path[0] === "source-images") return 30_000;
  return 15_000;
}

async function handler(
  request,
  context,
) {
  const { path = [] } = await context.params;

  return proxyToBackend(
    request,
    backendPath("/api/calibrations", path),
    {
      timeoutMs: calibrationProxyTimeout(
        request.method,
        path,
      ),
    },
  );
}

export {
  handler as DELETE,
  handler as GET,
  handler as PATCH,
  handler as POST,
  handler as PUT,
};

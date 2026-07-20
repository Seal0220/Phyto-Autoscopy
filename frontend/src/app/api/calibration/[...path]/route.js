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
  if (method === "GET" && path.at(-1) === "export") return 120_000;
  if (["solve", "apply", "validate"].includes(path.at(-1))) return 180_000;
  if (["capture", "detection", "reconnect"].includes(path.at(-1))) return 60_000;
  return method === "GET" ? 20_000 : 60_000;
}

async function handler(
  request,
  context,
) {
  const { path = [] } = await context.params;

  return proxyToBackend(
    request,
    backendPath("/api/calibration", path),
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

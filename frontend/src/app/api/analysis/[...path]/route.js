import {
  backendPath,
  proxyToBackend,
} from "@/lib/apiProxy";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

function analysisProxyTimeout(
  method,
  path,
) {
  if (
    method === "POST"
    && ["validate", "retry"].includes(path.at(-1))
  ) {
    return 120_000;
  }
  if (method === "GET" && path.at(-1) === "export") {
    return 120_000;
  }
  if (method === "GET" && path[0] === "sources") {
    return 60_000;
  }
  return 30_000;
}

async function handler(
  request,
  context,
) {
  const { path = [] } = await context.params;

  return proxyToBackend(
    request,
    backendPath("/api/analysis", path),
    {
      timeoutMs: analysisProxyTimeout(
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

import {
  backendPath,
  proxyToBackend,
} from "@/lib/apiProxy";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

async function handler(
  request,
  context,
) {
  const { path = [] } = await context.params;
  return proxyToBackend(
    request,
    backendPath("/api/system", path),
  );
}

export {
  handler as GET,
  handler as POST,
};

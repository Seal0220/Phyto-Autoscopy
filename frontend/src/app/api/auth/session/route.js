import { NextResponse } from "next/server";

import { getSession } from "@/lib/session";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  let session;
  try {
    session = await getSession();
  } catch (error) {
    console.error("Session lookup failed", {
      type: error instanceof Error ? error.name : typeof error,
    });
    return NextResponse.json(
      {
        detail: "登入狀態暫時無法確認，請稍後再試。",
        code: "AUTH_SERVICE_UNAVAILABLE",
        retryable: true,
      },
      {
        status: 503,
        headers: {
          "Cache-Control": "no-store",
          "Retry-After": "1",
        },
      },
    );
  }
  if (!session) {
    return NextResponse.json(
      {
        detail: "請先登入。",
        code: "SESSION_REQUIRED",
        retryable: false,
      },
      {
        status: 401,
        headers: { "Cache-Control": "no-store" },
      },
    );
  }
  return NextResponse.json(
    {
      actor: session.actor,
      role: session.role,
    },
    { headers: { "Cache-Control": "no-store" } },
  );
}

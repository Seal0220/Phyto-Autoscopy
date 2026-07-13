import { NextResponse } from "next/server";

import { clearSession } from "@/lib/session";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST() {
  try {
    await clearSession();
  } catch (error) {
    console.error("Session logout failed", {
      type: error instanceof Error ? error.name : typeof error,
    });
    return NextResponse.json(
      {
        detail: "登出服務暫時無法使用，請稍後再試。",
        code: "AUTH_SERVICE_UNAVAILABLE",
        retryable: false,
      },
      {
        status: 503,
        headers: { "Cache-Control": "no-store" },
      },
    );
  }
  return NextResponse.json(
    { ok: true },
    { headers: { "Cache-Control": "no-store" } },
  );
}

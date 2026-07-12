import { NextResponse } from "next/server";

import { getSession } from "@/lib/session";

export async function GET() {
  const session = await getSession();
  if (!session) {
    return NextResponse.json({ detail: "請先登入。" }, { status: 401 });
  }
  return NextResponse.json({ actor: session.actor, role: session.role });
}

import { NextResponse } from "next/server";

import { getSession } from "@/lib/session";

export async function GET() {
  const session = await getSession();
  if (!session) {
    return NextResponse.json({ detail: "Authentication required." }, { status: 401 });
  }
  return NextResponse.json({ actor: session.actor, role: session.role });
}

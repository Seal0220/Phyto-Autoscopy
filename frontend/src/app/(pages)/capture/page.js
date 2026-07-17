import { redirect } from "next/navigation";

import ControlPanel from "@/features/ControlPanel/ControlPanel";
import { getSession } from "@/lib/session";

export const dynamic = "force-dynamic";

export const metadata = {
  title: "捕捉 | Phyto-Autoscopy",
};

export default async function CapturePage() {
  const session = await getSession();

  if (!session) {
    redirect("/");
  }

  return <ControlPanel />;
}

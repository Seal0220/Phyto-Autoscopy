import { redirect } from "next/navigation";

import Analysis from "@/features/Analysis/Analysis";
import { getSession } from "@/lib/session";

export const dynamic = "force-dynamic";

export const metadata = {
  title: "分析 | Phyto-Autoscopy",
};

export default async function AnalysisPage() {
  const session = await getSession();

  if (!session) {
    redirect("/");
  }

  return <Analysis />;
}

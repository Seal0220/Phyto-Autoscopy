import { redirect } from "next/navigation";

import AnalysisNew from "@/features/Analysis/AnalysisNew";
import { getSession } from "@/lib/session";

export const dynamic = "force-dynamic";

export const metadata = {
  title: "新增分析 | Phyto-Autoscopy",
};

export default async function AnalysisNewPage({
  searchParams,
}) {
  const session = await getSession();

  if (!session) {
    redirect("/");
  }

  const parameters = await searchParams;
  const initialRecordId = typeof parameters?.record === "string"
    ? parameters.record.slice(0, 160)
    : "";

  return (
    <AnalysisNew
      initialRecordId={initialRecordId}
    />
  );
}

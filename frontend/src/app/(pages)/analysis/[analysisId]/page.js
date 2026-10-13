import {
  notFound,
  redirect,
} from "next/navigation";

import AnalysisRun from "@/features/AnalysisRun/AnalysisRun";
import { isValidAnalysisId } from "@/features/AnalysisRun/lib/analysisRunUtils";
import { getSession } from "@/lib/session";

export const dynamic = "force-dynamic";

export const metadata = {
  title: "分析紀錄 | Phyto-Autoscopy",
};

export default async function AnalysisRunPage({
  params,
  searchParams,
}) {
  const session = await getSession();

  if (!session) {
    redirect("/");
  }

  const { analysisId } = await params;
  if (!isValidAnalysisId(analysisId)) {
    notFound();
  }

  const query = await searchParams;
  const initialRoundKey = typeof query?.round_key === "string" && query.round_key.length <= 512
    ? query.round_key : undefined;
  const initialTipFilter = query?.tip_filter === "missing" ? "missing" : "all";
  return (
    <AnalysisRun
      key={`${analysisId}:${initialRoundKey || ""}:${initialTipFilter}`}
      analysisId={analysisId}
      initialRoundKey={initialRoundKey}
      initialTipFilter={initialTipFilter}
    />
  );
}

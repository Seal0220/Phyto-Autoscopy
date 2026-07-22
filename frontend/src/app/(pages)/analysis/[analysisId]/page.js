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
}) {
  const session = await getSession();

  if (!session) {
    redirect("/");
  }

  const { analysisId } = await params;
  if (!isValidAnalysisId(analysisId)) {
    notFound();
  }

  return <AnalysisRun analysisId={analysisId} />;
}

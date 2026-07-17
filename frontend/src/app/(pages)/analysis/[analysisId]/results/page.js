import {
  notFound,
  redirect,
} from "next/navigation";

import { isValidAnalysisId } from "@/features/AnalysisRun/lib/analysisRunUtils";
import TrajectoryViewer from "@/features/TrajectoryViewer/TrajectoryViewer";
import { getSession } from "@/lib/session";

export const dynamic = "force-dynamic";

export const metadata = {
  title: "分析結果 | Phyto-Autoscopy",
};

export default async function AnalysisResultsPage({
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

  return <TrajectoryViewer analysisId={analysisId} />;
}

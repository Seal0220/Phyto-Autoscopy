import {
  notFound,
  redirect,
} from "next/navigation";

import { isValidAnalysisId } from "@/features/AnalysisRun/lib/analysisRunUtils";
import TipReview from "@/features/TipReview/TipReview";
import { getSession } from "@/lib/session";

export const dynamic = "force-dynamic";

export const metadata = {
  title: "人工修正 | Phyto-Autoscopy",
};

export default async function TipReviewPage({
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
  const initialRoundKey = typeof query?.round_key === "string" && query.round_key.length <= 512 ? query.round_key : undefined;
  return <TipReview analysisId={analysisId} initialRoundKey={initialRoundKey} />;
}

import { notFound, redirect } from "next/navigation";

import CalibrationDetail from "@/features/Calibration/CalibrationDetail";
import { isValidCalibrationId } from "@/features/Calibration/lib/calibrationUtils";
import { getSession } from "@/lib/session";

export const dynamic = "force-dynamic";

export const metadata = {
  title: "校正工作流 | Phyto-Autoscopy",
};

export default async function CalibrationDetailPage({
  params,
}) {
  const session = await getSession();

  if (!session) {
    redirect("/");
  }

  const parameters = await params;
  const calibrationId = parameters?.calibrationId;

  if (!isValidCalibrationId(calibrationId)) {
    notFound();
  }

  return <CalibrationDetail calibrationId={calibrationId} />;
}

import { redirect } from "next/navigation";

import Calibration from "@/features/Calibration/Calibration";
import { getSession } from "@/lib/session";

export const dynamic = "force-dynamic";

export const metadata = {
  title: "校正 | Phyto-Autoscopy",
};

export default async function CalibrationPage() {
  const session = await getSession();

  if (!session) {
    redirect("/");
  }

  return <Calibration />;
}

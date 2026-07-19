import { redirect } from "next/navigation";

import { getSession } from "@/lib/session";

export const dynamic = "force-dynamic";

export const metadata = {
  title: "相機校正 | Phyto-Autoscopy",
};

export default async function CalibrationPage() {
  const session = await getSession();

  if (!session) {
    redirect("/");
  }

  redirect("/analysis#camera-calibration");
}

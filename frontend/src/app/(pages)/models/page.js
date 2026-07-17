import { redirect } from "next/navigation";

import Models from "@/features/Models/Models";
import { getSession } from "@/lib/session";

export const dynamic = "force-dynamic";

export const metadata = {
  title: "模型 | Phyto-Autoscopy",
};

export default async function ModelsPage() {
  const session = await getSession();

  if (!session) {
    redirect("/");
  }

  return <Models />;
}

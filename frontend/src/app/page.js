import ControlPanel from "@/features/ControlPanel/ControlPanel";
import LoginForm from "@/features/Login/LoginForm";
import { getSession } from "@/lib/session";

export const dynamic = "force-dynamic";

export default async function HomePage() {
  const session = await getSession();
  if (!session) {
    return <LoginForm />;
  }
  return <ControlPanel />;
}

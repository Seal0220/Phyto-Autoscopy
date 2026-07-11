import Dashboard from "@/components/dashboard";
import LoginForm from "@/components/login-form";
import { getSession } from "@/lib/session";

export const dynamic = "force-dynamic";

export default async function HomePage() {
  const session = await getSession();
  if (!session) {
    return <LoginForm />;
  }
  return <Dashboard actor={session.actor} />;
}

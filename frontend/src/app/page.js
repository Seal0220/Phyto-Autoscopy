import LoginForm from "@/features/Auth/LoginForm";
import Dashboard from "@/features/Dashboard/Dashboard";
import { getSession } from "@/lib/session";

export const dynamic = "force-dynamic";

export default async function HomePage() {
  const session = await getSession();
  if (!session) {
    return <LoginForm />;
  }
  return <Dashboard />;
}

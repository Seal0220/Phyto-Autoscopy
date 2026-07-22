import "./globals.css";
import localFont from "next/font/local";

import MainNavigation from "@/features/MainNavigation/MainNavigation";
import NotificationsProvider from "@/features/Notifications/components/NotificationsProvider";
import PhytoSocketProvider from "@/hooks/PhytoSocketProvider";
import { getSession } from "@/lib/session";

const chiron = localFont({
  src: "../../public/fonts/ChironGoRoundTC-VariableFont_wght.ttf",
  variable: "--font-chiron",
  display: "swap",
  weight: "100 900",
});

export const metadata = {
  title: "Phyto-Autoscopy",
  description: "Phyto-Autoscopy 本機捕捉與分析介面",
};

export default async function RootLayout({ children }) {
  const session = await getSession();

  return (
    <html lang="zh-Hant" className="scroll-smooth" suppressHydrationWarning>
      <body className={`${chiron.variable} min-w-[320px] overflow-x-hidden bg-[#06100c] text-white antialiased [font-family:var(--font-chiron)]`}>
        <NotificationsProvider>
          {session ? (
            <PhytoSocketProvider>
              <main className="min-h-screen bg-[#06100c] px-5 pb-8 max-sm:px-3">
                <MainNavigation />
                {children}
              </main>
            </PhytoSocketProvider>
          ) : children}
        </NotificationsProvider>
      </body>
    </html>
  );
}

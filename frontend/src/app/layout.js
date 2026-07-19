import "./globals.css";
import localFont from "next/font/local";

import NotificationsProvider from "@/features/Notifications/components/NotificationsProvider";

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

export default function RootLayout({ children }) {
  return (
    <html lang="zh-Hant" className="scroll-smooth" suppressHydrationWarning>
      <body className={`${chiron.variable} min-w-[320px] overflow-x-hidden bg-[#06100c] text-white antialiased [font-family:var(--font-chiron)]`}>
        <NotificationsProvider>
          {children}
        </NotificationsProvider>
      </body>
    </html>
  );
}

import "./globals.css";
import localFont from "next/font/local";

const chiron = localFont({
  src: "../../public/fonts/ChironGoRoundTC-VariableFont_wght.ttf",
  variable: "--font-chiron",
  display: "swap",
  weight: "100 900",
});

export const metadata = {
  title: "Phyto-Autoscopy | 控制介面",
  description: "CHLOROCULUS local control interface",
};

export default function RootLayout({ children }) {
  return (
    <html lang="zh-Hant" className="scroll-smooth">
      <body className={`${chiron.variable} min-w-[320px] overflow-x-hidden bg-[#06100c] text-white antialiased [font-family:var(--font-chiron)]`}>
        {children}
      </body>
    </html>
  );
}

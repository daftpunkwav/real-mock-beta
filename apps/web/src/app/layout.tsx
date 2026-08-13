import type { Metadata, Viewport } from "next";
import { DM_Sans, JetBrains_Mono } from "next/font/google";
import "./globals.css";
import { AppShell } from "@/components/layout/AppShell";
import { Toaster } from "@/components/Toast";
import { ThemeProvider, themeInitScript } from "@/components/theme/ThemeProvider";

const dmSans = DM_Sans({
  subsets: ["latin"],
  variable: "--font-dm-sans",
  display: "swap",
  weight: ["400", "500", "600", "700"],
});

const jetbrains = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-jetbrains",
  display: "swap",
  weight: ["400", "500"],
});

export const metadata: Metadata = {
  title: "RealMock — AI 智能模拟面试",
  description: "基于 AI Agent 的真实面试模拟系统，支持 BYOK",
  applicationName: "RealMock",
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#ffffff" },
    { media: "(prefers-color-scheme: dark)", color: "#161616" },
  ],
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeInitScript }} />
      </head>
      <body
        className={`${dmSans.variable} ${jetbrains.variable} font-sans antialiased text-[var(--foreground)] bg-[var(--background)]`}
      >
        <ThemeProvider>
          <AppShell>{children}</AppShell>
          <Toaster />
        </ThemeProvider>
      </body>
    </html>
  );
}

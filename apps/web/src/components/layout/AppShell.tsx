"use client";

import { usePathname } from "next/navigation";
import { Sidebar } from "./Sidebar";

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const isFullscreen = /^\/interview\/\d+/.test(pathname);
  const isFixedHeightPage = pathname === "/prep" || pathname === "/interview";

  // 面试房间页默认沿用用户/系统主题,不再强制覆盖为 dark。
  if (isFullscreen) {
    return (
      <main className="h-screen w-screen overflow-hidden bg-[var(--background)] text-[var(--foreground)]">
        {children}
      </main>
    );
  }

  return (
    <div className="flex min-h-screen flex-col lg:flex-row bg-[var(--background)]">
      <Sidebar />
      <main
        className={
          isFixedHeightPage
            ? "flex-1 min-h-0 lg:h-screen overflow-hidden"
            : "flex-1 overflow-y-auto [scrollbar-gutter:stable]"
        }
      >
        {children}
      </main>
    </div>
  );
}

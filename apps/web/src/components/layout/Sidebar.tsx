"use client";

/** 侧栏主壳:移动端顶栏/遮罩/抽屉 + 桌面折叠。导航内容见 SidebarNav。 */

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { ChevronLeft, ChevronRight, Menu, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { NavContent } from "./SidebarNav";

export function Sidebar() {
  const pathname = usePathname();
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);

  useEffect(() => {
    setMobileOpen(false);
  }, [pathname]);

  useEffect(() => {
    if (!mobileOpen) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = prev;
    };
  }, [mobileOpen]);

  return (
    <>
      {/* 移动端顶栏 */}
      <div className="sticky top-0 z-30 flex h-12 items-center gap-3 border-b border-surface-border bg-surface-card/95 px-4 backdrop-blur-md lg:hidden">
        <button
          type="button"
          onClick={() => setMobileOpen(true)}
          className="btn-ghost !h-9 !w-9"
          aria-label="打开导航"
        >
          <Menu size={18} />
        </button>
        <Link href="/" className="flex items-center gap-2">
          <span className="g-logo-dot-sm" aria-hidden />
          <span className="text-[14px] font-semibold text-ink">RealMock</span>
        </Link>
      </div>

      {/* 移动端遮罩 */}
      <AnimatePresence>
        {mobileOpen && (
          <motion.div
            className="fixed inset-0 z-40 bg-black/40 lg:hidden"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={() => setMobileOpen(false)}
          />
        )}
      </AnimatePresence>

      {/* 移动端抽屉 */}
      <AnimatePresence>
        {mobileOpen && (
          <motion.aside
            className="fixed inset-y-0 left-0 z-50 flex w-72 flex-col border-r border-[var(--sidebar-border)] bg-[var(--sidebar)] shadow-lg lg:hidden"
            initial={{ x: -288 }}
            animate={{ x: 0 }}
            exit={{ x: -288 }}
            transition={{ type: "spring", stiffness: 420, damping: 38 }}
          >
            <button
              type="button"
              onClick={() => setMobileOpen(false)}
              className="btn-ghost absolute right-3 top-3 !h-8 !w-8"
              aria-label="关闭导航"
            >
              <X size={16} />
            </button>
            <NavContent collapsed={false} onNavigate={() => setMobileOpen(false)} />
          </motion.aside>
        )}
      </AnimatePresence>

      {/* 桌面侧栏 */}
      <motion.aside
        className={cn(
          "sticky top-0 z-20 hidden h-screen shrink-0 flex-col border-r border-[var(--sidebar-border)] bg-[var(--sidebar)] lg:flex",
          collapsed ? "w-[64px]" : "w-[248px]",
        )}
        initial={false}
        animate={{ width: collapsed ? 64 : 248 }}
        transition={{ duration: 0.22, ease: [0.2, 0, 0, 1] }}
      >
        <NavContent collapsed={collapsed} />

        {/* 桌面收起 / 展开按钮 */}
        <button
          type="button"
          className={cn(
            "group absolute -right-3 top-[68px] z-30 flex items-center gap-1.5 rounded-full border border-surface-border bg-surface-card text-ink-muted shadow-md transition-all duration-base ease-google hover:border-[var(--primary)] hover:text-[var(--primary)] hover:shadow-brand active:scale-95",
            collapsed ? "h-7 px-2 text-[10px] font-medium" : "h-7 w-7 justify-center",
          )}
          onClick={() => setCollapsed(!collapsed)}
          aria-label={collapsed ? "展开侧栏" : "收起侧栏"}
          title={collapsed ? "展开侧栏" : "收起侧栏"}
        >
          {collapsed ? (
            <>
              <ChevronRight
                size={12}
                className="transition-transform duration-base group-hover:translate-x-0.5"
              />
              <span className="opacity-0 transition-opacity duration-base group-hover:opacity-100">
                展开
              </span>
            </>
          ) : (
            <ChevronLeft
              size={13}
              className="transition-transform duration-base group-hover:-translate-x-0.5"
            />
          )}
          <span
            className="pointer-events-none absolute inset-0 rounded-full ring-[3px] ring-[var(--primary)]/0 transition-all duration-base ease-google group-hover:ring-[3px] group-hover:ring-[var(--primary)]/25"
            aria-hidden
          />
        </button>
      </motion.aside>
    </>
  );
}

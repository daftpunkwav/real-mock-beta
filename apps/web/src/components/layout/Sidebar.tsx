"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { ChevronLeft, ChevronRight, Menu, X } from "lucide-react";
import { NAV_ITEMS } from "@/config/nav";
import { cn } from "@/lib/utils";
import { ThemeToggle } from "@/components/theme/ThemeToggle";

function isNavActive(pathname: string, href: string): boolean {
  if (href === "/") return pathname === "/";
  if (href === "/interview") {
    return pathname === "/interview" || pathname.startsWith("/interview/");
  }
  if (href === "/history") {
    return pathname === "/history" || pathname.startsWith("/report/");
  }
  return pathname === href || pathname.startsWith(`${href}/`);
}

function NavContent({
  collapsed,
  onNavigate,
}: {
  collapsed: boolean;
  onNavigate?: () => void;
}) {
  const pathname = usePathname();

  return (
    <>
      {/* Logo */}
      <div className="flex h-[60px] items-center justify-between overflow-hidden border-b border-[var(--sidebar-border)] px-4">
        <Link
          href="/"
          onClick={onNavigate}
          className="group flex min-w-0 items-center gap-2.5"
        >
          <span className="g-logo-dot shadow-xs" aria-hidden />
          <AnimatePresence initial={false}>
            {!collapsed && (
              <motion.div
                className="min-w-0 overflow-hidden"
                initial={{ opacity: 0, width: 0 }}
                animate={{ opacity: 1, width: "auto" }}
                exit={{ opacity: 0, width: 0 }}
                transition={{ duration: 0.16, ease: [0.2, 0, 0, 1] }}
              >
                <h1 className="whitespace-nowrap text-[15px] font-semibold tracking-tight text-[var(--sidebar-foreground)]">
                  RealMock
                </h1>
                <p className="whitespace-nowrap text-[10px] uppercase tracking-[0.1em] text-[var(--muted-foreground)]">
                  AI Mock Interview
                </p>
              </motion.div>
            )}
          </AnimatePresence>
        </Link>
      </div>

      {/* 导航 */}
      <nav
        className="flex-1 space-y-0.5 overflow-y-auto px-2.5 py-3"
        aria-label="主导航"
      >
        <AnimatePresence>
          {!collapsed && (
            <motion.p
              key="nav-label"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="px-2.5 pb-2 pt-1 text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--muted-foreground)]"
            >
              Workspace
            </motion.p>
          )}
        </AnimatePresence>

        {NAV_ITEMS.filter((item) => !item.hidden).map(({ href, label, icon: Icon }) => {
          const isActive = isNavActive(pathname, href);
          return (
            <Link
              key={href}
              href={href}
              onClick={onNavigate}
              className="block"
              title={collapsed ? label : undefined}
              aria-current={isActive ? "page" : undefined}
            >
              <div
                className={cn(
                  "group/nav relative flex items-center gap-2.5 rounded-md px-2.5 py-2 text-[13px] transition-colors duration-base ease-google",
                  isActive
                    ? "bg-[var(--sidebar-active)] font-medium text-[var(--sidebar-accent-foreground)]"
                    : "text-[var(--sidebar-foreground)] hover:bg-[var(--sidebar-hover)]",
                )}
              >
                {/* 激活态左侧 3px 指示条 */}
                {isActive && (
                  <span
                    className="absolute left-0 top-1/2 h-5 w-[3px] -translate-y-1/2 rounded-r-full bg-[var(--sidebar-primary)]"
                    aria-hidden
                  />
                )}
                <Icon
                  size={17}
                  strokeWidth={isActive ? 2 : 1.75}
                  className={cn(
                    "shrink-0 transition-all duration-base ease-google group-hover/nav:scale-110",
                    isActive
                      ? "text-[var(--sidebar-primary)]"
                      : "text-[var(--muted-foreground)] group-hover/nav:text-[var(--sidebar-foreground)]",
                  )}
                />
                {!collapsed && (
                  <span className="min-w-0 flex-1 truncate">{label}</span>
                )}
                {href === "/interview" && !collapsed && (
                  <span className="chip chip-blue !px-1.5 !py-0 !text-[10px]">Hot</span>
                )}
                {!collapsed && (
                  <ChevronRight
                    size={13}
                    className={cn(
                      "shrink-0 -translate-x-1 text-ink-subtle opacity-0 transition-all duration-base ease-google group-hover/nav:translate-x-0 group-hover/nav:opacity-100",
                      isActive && "text-[var(--sidebar-primary)] opacity-60 translate-x-0",
                    )}
                  />
                )}
              </div>
            </Link>
          );
        })}
      </nav>

      {/* 底部状态条 + 主题切换 */}
      <div className="border-t border-[var(--sidebar-border)] px-1 pt-2">
        <ThemeToggle collapsed={collapsed} />
        {!collapsed && (
          <div className="mx-3 mb-3 flex items-center gap-2 px-1 text-[11px] text-[var(--muted-foreground)]">
            <span className="relative flex h-1.5 w-1.5">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-[var(--success)] opacity-40" />
              <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-[var(--success)]" />
            </span>
            <span className="font-medium">开源 · BYOK · 本地优先</span>
          </div>
        )}
      </div>
    </>
  );
}

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

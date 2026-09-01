"use client";

/** 面试配置页骨架：顶部标题（含开始按钮位）/ 加载态 / 主双栏布局（表单区 + 右侧预览）。 */

import { Sparkles } from "lucide-react";
import type { ReactNode } from "react";

export function SetupHeader({ action }: { action?: ReactNode }) {
  return (
    <div className="mb-4 flex shrink-0 items-center justify-between gap-4">
      <div className="page-header !mb-0 min-w-0">
        <div className="flex items-start gap-3">
          <span className="icon-badge icon-badge-brand shrink-0">
            <Sparkles size={18} strokeWidth={1.75} />
          </span>
          <div className="min-w-0">
            <p className="page-eyebrow">Mock Setup</p>
            <h1 className="page-title !text-[20px]">配置模拟面试</h1>
            <p className="page-desc !text-xs">定制你的专属面试体验</p>
          </div>
        </div>
      </div>
      {action ? <div className="hidden sm:block">{action}</div> : null}
    </div>
  );
}

export function SetupLoading() {
  return (
    <div className="flex flex-1 items-center justify-center gap-2 text-[13px] text-ink-muted">
      <span className="block h-4 w-4 anim-spin rounded-full border-2 border-current border-t-transparent" />
      加载配置中…
    </div>
  );
}

export function SetupMain({ left, preview }: { left: ReactNode; preview: ReactNode }) {
  return (
    <div className="grid min-h-0 flex-1 grid-cols-1 gap-3 overflow-hidden lg:grid-cols-[1fr_260px]">
      {left}
      <div className="hidden min-h-0 flex-col gap-2.5 overflow-hidden lg:flex">{preview}</div>
    </div>
  );
}

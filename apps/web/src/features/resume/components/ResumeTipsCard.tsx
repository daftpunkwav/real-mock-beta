"use client";

import { Lightbulb } from "lucide-react";

/** 右侧提示卡。 */
export function ResumeTipsCard() {
  return (
    <div className="surface-card p-4 sm:p-5">
      <h2 className="mb-2.5 flex items-center gap-2 text-[13px] font-semibold tracking-tight text-ink">
        <Lightbulb size={14} className="text-[var(--primary)]" />
        提示
      </h2>
      <ul className="space-y-2 text-[11px] leading-relaxed text-ink-subtle">
        <li>· 「投递简历」会关联到模拟面试与面试准备</li>
        <li>· 深度评价会联网检索岗位要求,并点评排版、字体与内容</li>
        <li>· 旧评价需重新点击「AI 深度评价」才会刷新新结构</li>
      </ul>
    </div>
  );
}

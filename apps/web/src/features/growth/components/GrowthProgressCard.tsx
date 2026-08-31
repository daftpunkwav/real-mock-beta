"use client";

import Link from "next/link";

/** 成长完成度卡：进度条 + 引导按钮。 */
export function GrowthProgressCard({ growthPct }: { growthPct: number }) {
  return (
    <div className="surface-card p-5">
      <div className="mb-2 flex items-center justify-between">
        <span className="text-[13px] font-medium text-ink">成长完成度</span>
        <span className="font-mono text-[13px] font-semibold text-[var(--primary)] num-tabular">
          {growthPct}%
        </span>
      </div>
      <div className="progress">
        <div
          className="progress-bar"
          style={{
            background:
              "linear-gradient(90deg, var(--chart-3), var(--chart-2))",
            width: `${growthPct}%`,
          }}
        />
      </div>
      <p className="mt-2.5 text-[11px] leading-relaxed text-ink-subtle">
        多完成面试并执行训练计划,可提升完成度。
      </p>
      <div className="mt-4 grid grid-cols-2 gap-2">
        <Link href="/interview" className="btn-secondary !h-9 !text-xs">
          模拟面试
        </Link>
        <Link href="/prep" className="btn-secondary !h-9 !text-xs">
          面试准备
        </Link>
      </div>
    </div>
  );
}

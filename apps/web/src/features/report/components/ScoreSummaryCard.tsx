"use client";

import Link from "next/link";
import { ArrowLeft, FileBarChart } from "lucide-react";
import { formatScore, scoreColor } from "../scoreFormat";

/** 报告页头部:返回记录链接 + 标题/时长 + 综合评分。 */
export function ScoreSummaryCard({
  duration,
  messagesCount,
  overallScore,
}: {
  duration?: number;
  messagesCount?: number;
  overallScore: number | null | undefined;
}) {
  return (
    <>
      <Link
        href="/history"
        className="mb-6 flex w-fit items-center gap-1 text-[12px] text-ink-subtle hover:text-[var(--primary)]"
      >
        <ArrowLeft size={13} /> 返回记录
      </Link>

      <div className="surface-card mb-6 flex flex-col justify-between gap-4 p-5 sm:flex-row sm:items-center">
        <div className="flex items-start gap-3">
          <span className="icon-badge icon-badge-brand">
            <FileBarChart size={18} strokeWidth={1.75} />
          </span>
          <div>
            <p className="page-eyebrow">Report</p>
            <h1 className="page-title !mt-1">面试评估报告</h1>
            {duration != null && (
              <p className="mt-1.5 text-[12px] text-ink-subtle">
                面试时长:{duration} 分钟
                {typeof messagesCount === "number" ? ` · 有效对话 ${messagesCount} 条` : ""}
              </p>
            )}
          </div>
        </div>
        <div className="rounded-md border border-surface-border bg-surface-alt px-5 py-3 text-center sm:text-right">
          <div
            className="font-mono text-[36px] font-semibold leading-none tracking-tight num-tabular"
            style={{ color: scoreColor(overallScore) }}
          >
            {formatScore(overallScore)}
          </div>
          <div className="mt-1 text-[10px] font-semibold uppercase tracking-[0.1em] text-ink-subtle">
            综合评分 / 100
          </div>
        </div>
      </div>
    </>
  );
}

"use client";

import { BarChart3, Calendar, ListTodo, Target, TrendingUp } from "lucide-react";
import type { GrowthRecord } from "@/types";
import { PreviewRow } from "./PreviewRow";

/** 右侧成长卡：档位、统计行、重点关注、当前计划。 */
export function GrowthSummaryCard({
  growthLevel,
  totalInterviews,
  totalPlans,
  totalWeakSkills,
  selected,
  topWeaknesses,
}: {
  growthLevel: string;
  totalInterviews: number;
  totalPlans: number;
  totalWeakSkills: number;
  selected: GrowthRecord | null;
  topWeaknesses: [string, number][];
}) {
  return (
    <div className="surface-card p-5">
      <div className="mb-4 flex items-center gap-3">
        <div
          className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full text-white"
          style={{
            background:
              "linear-gradient(135deg, var(--chart-3), var(--chart-2))",
          }}
        >
          <TrendingUp size={20} strokeWidth={2} />
        </div>
        <div className="min-w-0">
          <h2 className="text-[15px] font-semibold tracking-tight text-ink">{growthLevel}</h2>
          <p className="mt-0.5 text-[11px] text-ink-subtle">
            {totalInterviews > 0
              ? `已积累 ${totalInterviews} 条成长记录`
              : "等待第一次面试"}
          </p>
        </div>
      </div>
      <dl className="space-y-2.5 text-sm">
        <PreviewRow icon={BarChart3} label="成长记录" value={`${totalInterviews} 场`} />
        <PreviewRow icon={ListTodo} label="训练计划" value={`${totalPlans} 项`} />
        <PreviewRow icon={Target} label="薄弱技能" value={`${totalWeakSkills} 个`} />
        {selected && (
          <PreviewRow
            icon={Calendar}
            label="最近训练"
            value={new Date(selected.created_at).toLocaleDateString("zh-CN")}
          />
        )}
      </dl>
      {topWeaknesses.length > 0 && (
        <div className="mt-4 border-t border-surface-border pt-3">
          <p className="mb-2 text-[10px] font-semibold uppercase tracking-[0.1em] text-ink-subtle">
            重点关注
          </p>
          <ul className="space-y-2">
            {topWeaknesses.slice(0, 4).map(([skill], i) => (
              <li
                key={skill}
                className="flex gap-2 text-[11px] leading-relaxed text-ink-muted"
              >
                <span className="font-mono shrink-0 font-semibold text-[var(--warning)] num-tabular">
                  {i + 1}.
                </span>
                <span className="line-clamp-2 min-w-0 break-words">{skill}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {selected && selected.training_plan.length > 0 && (
        <div className="mt-4 border-t border-surface-border pt-3">
          <p className="mb-1.5 text-[10px] font-semibold uppercase tracking-[0.1em] text-ink-subtle">
            当前计划
          </p>
          <ul className="space-y-1.5">
            {selected.training_plan.slice(0, 3).map((t, i) => (
              <li
                key={i}
                className="flex gap-1.5 text-[11px] leading-relaxed text-ink-muted"
              >
                <span className="shrink-0 font-semibold text-[var(--primary)]">{i + 1}.</span>
                <span className="line-clamp-2">{t}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

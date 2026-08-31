"use client";

import { AlertCircle, Target } from "lucide-react";
import { Section } from "./Section";

/** 高频薄弱项区块：前 5 弱项 + 出现次数 + 占比条，空态保持原文案。 */
export function TopWeaknessesSection({
  topWeaknesses,
  totalInterviews,
}: {
  topWeaknesses: [string, number][];
  totalInterviews: number;
}) {
  return (
    <Section title="高频薄弱项" icon={Target}>
      {topWeaknesses.length > 0 ? (
        <div className="space-y-3.5">
          {topWeaknesses.map(([skill, count], index) => (
            <div key={skill} className="flex items-start gap-3">
              <span className="icon-badge icon-badge-danger mt-0.5 shrink-0 !h-7 !w-7 !text-[11px]">
                {index + 1}
              </span>
              <div className="min-w-0 flex-1">
                <div className="mb-1 flex items-start justify-between gap-3 text-[13px]">
                  <span className="min-w-0 break-words font-medium leading-snug text-ink">
                    {skill}
                  </span>
                  <span className="shrink-0 whitespace-nowrap pt-0.5 text-[11px] text-ink-subtle">
                    出现 {count} 次
                  </span>
                </div>
                <div className="progress !h-1.5">
                  <div
                    className="progress-bar !bg-[var(--danger)]"
                    style={{
                      width: `${Math.min((count / Math.max(totalInterviews, 1)) * 100, 100)}%`,
                    }}
                  />
                </div>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="py-8 text-center">
          <AlertCircle className="mx-auto mb-2 text-ink-subtle" size={26} />
          <p className="text-[13px] text-ink-subtle">完成模拟面试后将自动汇总薄弱技能</p>
        </div>
      )}
    </Section>
  );
}

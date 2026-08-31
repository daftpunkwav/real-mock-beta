"use client";

import Link from "next/link";
import { Award, Play } from "lucide-react";
import type { GrowthRecord } from "@/types";
import { Section } from "./Section";

/** 训练历史区块：按会话列出记录，空态引导开始面试。 */
export function TrainingHistorySection({
  records,
  selectedId,
  onSelect,
}: {
  records: GrowthRecord[];
  selectedId: number | null;
  onSelect: (id: number) => void;
}) {
  return (
    <Section title="训练历史" icon={Award}>
      {records.length > 0 ? (
        <div className="space-y-2">
          {records.map((r) => {
            const active = selectedId === r.id;
            return (
              <button
                key={r.id}
                type="button"
                onClick={() => onSelect(r.id)}
                className={`w-full rounded-md border px-4 py-3.5 text-left transition-colors ${
                  active
                    ? "border-[var(--primary)] bg-[var(--info-soft)]"
                    : "border-surface-border hover:border-surface-strong hover:bg-surface-alt"
                }`}
              >
                <div className="mb-1 flex items-center justify-between gap-2">
                  <span className="text-[13px] font-semibold text-ink">
                    面试 #{r.session_id}
                  </span>
                  <Link
                    href={`/report/${r.session_id}`}
                    onClick={(e) => e.stopPropagation()}
                    className="text-[11px] font-medium text-[var(--primary)] hover:underline"
                  >
                    报告 →
                  </Link>
                </div>
                <p className="mb-2 text-[11px] text-ink-subtle">
                  {new Date(r.created_at).toLocaleString("zh-CN")}
                </p>
                {r.weak_skills.length > 0 && (
                  <div className="mb-2 flex flex-wrap gap-1">
                    {r.weak_skills.map((s) => (
                      <span key={s} className="chip chip-red !text-[10px]">
                        {s}
                      </span>
                    ))}
                  </div>
                )}
                {r.training_plan.length > 0 && (
                  <p className="line-clamp-2 text-[11px] leading-relaxed text-ink-muted">
                    {r.training_plan[0]}
                  </p>
                )}
              </button>
            );
          })}
        </div>
      ) : (
        <div className="py-10 text-center">
          <Award className="mx-auto mb-3 text-ink-subtle" size={28} />
          <p className="mb-4 text-[13px] text-ink-subtle">完成面试后将生成成长记录</p>
          <Link href="/interview" className="btn-primary !h-9">
            <Play size={13} />
            开始模拟面试
          </Link>
        </div>
      )}
    </Section>
  );
}

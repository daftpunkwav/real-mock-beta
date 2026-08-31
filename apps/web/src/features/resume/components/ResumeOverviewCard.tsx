"use client";

import { Gauge } from "lucide-react";
import type { Resume } from "@/types";

/** 右侧概览卡：已上传 / 已评分 / 当前投递。 */
export function ResumeOverviewCard({ resumes }: { resumes: Resume[] }) {
  const activeResume = resumes.find((r) => r.is_active);
  return (
    <div className="surface-card p-4 sm:p-5">
      <h2 className="mb-3 flex items-center gap-2 text-[13px] font-semibold tracking-tight text-ink">
        <Gauge size={14} className="text-[var(--warning)]" />
        概览
      </h2>
      <div className="grid grid-cols-2 gap-2">
        <div className="kpi-card !p-3">
          <p className="kpi-value !text-xl">{resumes.length}</p>
          <p className="kpi-label mt-1">已上传</p>
        </div>
        <div className="kpi-card !p-3">
          <p className="kpi-value !text-xl">{resumes.filter((r) => r.score != null).length}</p>
          <p className="kpi-label mt-1">已评分</p>
        </div>
      </div>
      {activeResume && (
        <p className="mt-3 border-t border-surface-border pt-3 text-[11px] leading-relaxed text-ink-subtle">
          当前投递:
          <span className="ml-1 font-medium text-ink">{activeResume.filename}</span>
        </p>
      )}
    </div>
  );
}

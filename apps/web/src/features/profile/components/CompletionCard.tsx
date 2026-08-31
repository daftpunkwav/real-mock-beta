"use client";

import { CheckCircle2 } from "lucide-react";
import { REQUIRED_KEYS, REQUIRED_LABELS, OPTIONAL_COMPLETION_KEYS } from "../profileRules";
import type { ProfileCompletionStats } from "../profileRules";

export function CompletionCard({ stats }: { stats: ProfileCompletionStats }) {
  const { completionPct, requiredDone, optionalDone, requiredMissing } = stats;
  return (
    <div className="surface-card p-5">
      <div className="mb-2.5 flex items-center justify-between">
        <span className="text-[13px] font-semibold tracking-tight text-ink">
          档案完整度
        </span>
        <span className="font-mono text-[14px] font-semibold text-[var(--primary)] num-tabular">
          {completionPct}%
        </span>
      </div>
      <div className="progress">
        <div
          className="progress-bar anim-progress-fill"
          style={{ width: `${completionPct}%` }}
        />
      </div>
      <div className="mt-3 grid grid-cols-2 gap-2 text-center">
        <div className="kpi-card !p-2.5">
          <p className="font-mono text-[15px] font-semibold text-ink num-tabular">
            {requiredDone}/{REQUIRED_KEYS.length}
          </p>
          <p className="kpi-label mt-0.5">必填</p>
        </div>
        <div className="kpi-card !p-2.5">
          <p className="font-mono text-[15px] font-semibold text-ink num-tabular">
            {optionalDone}/{OPTIONAL_COMPLETION_KEYS.length}
          </p>
          <p className="kpi-label mt-0.5">选填</p>
        </div>
      </div>
      {requiredMissing.length > 0 ? (
        <div className="mt-3 rounded-md border border-[var(--danger)]/30 bg-[var(--danger-soft)] px-3 py-2">
          <p className="text-[11px] leading-relaxed text-[var(--danger-ink)]">
            待补必填:{requiredMissing.map((k) => REQUIRED_LABELS[k]).join("、")}
          </p>
        </div>
      ) : (
        <div className="mt-3 flex items-center gap-2 rounded-md border border-[var(--success)]/30 bg-[var(--success-soft)] px-3 py-2">
          <CheckCircle2 size={13} className="text-[var(--success)]" />
          <span className="text-[11px] font-medium text-[var(--success-ink)]">
            所有必填项已就绪
          </span>
        </div>
      )}
    </div>
  );
}

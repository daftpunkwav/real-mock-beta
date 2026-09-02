import type { ReactNode } from "react";
import { ExternalLink, FileText, Play, TrendingUp } from "lucide-react";
import Link from "next/link";
import type { InterviewSession } from "@/lib/api/contract";
import { StatusBadge } from "./StatusBadge";
import { StatCell } from "./StatCell";

/** 侧栏详情行：标签 + 值。 */
function DetailRow({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-3">
      <span className="shrink-0 pt-0.5 text-[10px] uppercase tracking-[0.08em] text-ink-subtle">
        {label}
      </span>
      <span className="text-right text-[13px] font-medium text-ink">{value}</span>
    </div>
  );
}

/** 侧栏：数据概览 + 选中场次详情与跳转动作。 */
export function HistoryDetailAside({
  selected,
  stats,
}: {
  selected: InterviewSession | null;
  stats: { total: number; completed: number; active: number; avgScore: number | null };
}) {
  return (
    <aside className="space-y-3 xl:sticky xl:top-6">
      <div className="surface-card p-5">
        <h2 className="mb-3.5 flex items-center gap-2 text-[13px] font-semibold tracking-tight text-ink">
          <TrendingUp size={14} className="text-[var(--primary)]" />
          数据概览
        </h2>
        <div className="grid grid-cols-2 gap-2">
          <StatCell value={stats.total} label="总场次" />
          <StatCell value={stats.completed} label="已完成" tone="success" />
          <StatCell value={stats.active} label="进行中" tone="info" />
          <StatCell value={stats.avgScore ?? "—"} label="平均分" />
        </div>
      </div>

      <div className="surface-card p-5">
        {selected ? (
          <>
            <h2 className="mb-3.5 text-[13px] font-semibold tracking-tight text-ink">
              场次详情
            </h2>
            <dl className="space-y-2.5 text-sm">
              <DetailRow label="岗位" value={`${selected.role} · ${selected.level}`} />
              <DetailRow label="公司" value={selected.company} />
              <DetailRow label="类型" value={selected.workflow_type} />
              <DetailRow label="状态" value={<StatusBadge status={selected.status} />} />
              <DetailRow
                label="时间"
                value={new Date(selected.created_at).toLocaleString("zh-CN")}
              />
              {selected.overall_score != null && (
                <DetailRow
                  label="综合评分"
                  value={
                    <span className="font-mono text-[16px] font-semibold text-[var(--primary)] num-tabular">
                      {selected.overall_score}
                    </span>
                  }
                />
              )}
              {selected.current_phase && selected.status === "active" && (
                <DetailRow label="当前阶段" value={selected.current_phase} />
              )}
            </dl>

            <div className="mt-5 border-t border-surface-border pt-4">
              {selected.status === "completed" ? (
                <Link href={`/report/${selected.id}`} className="btn-primary w-full">
                  <FileText size={13} />
                  查看报告
                  <ExternalLink size={13} />
                </Link>
              ) : selected.status === "active" ? (
                <Link href={`/interview/${selected.id}`} className="btn-primary w-full">
                  <Play size={13} />
                  继续面试
                </Link>
              ) : (
                <p className="py-1 text-center text-[11px] text-ink-subtle">该场次尚未开始</p>
              )}
            </div>
          </>
        ) : (
          <p className="py-6 text-center text-[13px] text-ink-subtle">选择一条记录查看详情</p>
        )}
      </div>
    </aside>
  );
}

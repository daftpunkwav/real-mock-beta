import { BarChart3, Play } from "lucide-react";
import Link from "next/link";
import type { InterviewSession } from "@/types";
import { StatusBadge } from "./StatusBadge";

/** 全部场次列表：标题 + 总数 chip + 空态（链到 /interview）或可选中列表。 */
export function HistoryListCard({
  sessions,
  selectedId,
  onSelect,
  total,
}: {
  sessions: InterviewSession[];
  selectedId: number | null;
  onSelect: (id: number) => void;
  total: number;
}) {
  return (
    <div className="surface-card overflow-hidden">
      <div className="flex items-center justify-between border-b border-surface-border px-4 py-3">
        <h2 className="text-[13px] font-semibold tracking-tight text-ink">全部场次</h2>
        <span className="chip chip-gray">{total} 场</span>
      </div>

      {sessions.length === 0 ? (
        <div className="empty-state !py-14">
          <div className="empty-state-icon">
            <BarChart3 size={22} />
          </div>
          <p className="mb-4 text-[13px]">暂无面试记录</p>
          <Link href="/interview" className="btn-primary !h-9">
            <Play size={13} />
            开始模拟面试
          </Link>
        </div>
      ) : (
        <ul className="divide-y divide-surface-border">
          {sessions.map((s) => {
            const active = selectedId === s.id;
            return (
              <li key={s.id}>
                <button
                  type="button"
                  onClick={() => onSelect(s.id)}
                  className={`flex w-full items-start gap-3 px-4 py-3.5 text-left transition-colors ${
                    active ? "bg-[var(--info-soft)]" : "hover:bg-surface-alt"
                  }`}
                >
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-[13px] font-medium text-ink">
                        {s.role} · {s.level}
                      </span>
                      <StatusBadge status={s.status} />
                    </div>
                    <p className="mt-1 text-[11px] text-ink-subtle">
                      {s.company} · {s.workflow_type} ·{" "}
                      {new Date(s.created_at).toLocaleString("zh-CN")}
                    </p>
                  </div>
                  <div className="shrink-0 text-right">
                    {s.overall_score != null && (
                      <p className="font-mono text-[18px] font-semibold leading-none text-[var(--primary)] num-tabular">
                        {s.overall_score}
                      </p>
                    )}
                  </div>
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

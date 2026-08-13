"use client";

import { useEffect, useState, useMemo, useCallback } from "react";
import Link from "next/link";
import { interviewService as api } from "@/lib/api/interviewService";
import type { InterviewSession } from "@/types";
import {
  ExternalLink,
  BarChart3,
  Clock,
  CheckCircle2,
  Circle,
  Play,
  FileText,
  TrendingUp,
} from "lucide-react";
import { LoadError } from "@/components/LoadError";

export default function HistoryPage() {
  const [sessions, setSessions] = useState<InterviewSession[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const list = await api.listSessions();
      setSessions(list);
      const firstCompleted = list.find((s) => s.status === "completed");
      const fallback = list[0];
      setSelectedId(firstCompleted?.id ?? fallback?.id ?? null);
    } catch (e) {
      setLoadError(e instanceof Error ? e.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const selected = useMemo(
    () => sessions.find((s) => s.id === selectedId) ?? null,
    [sessions, selectedId],
  );

  const stats = useMemo(
    () => ({
      total: sessions.length,
      completed: sessions.filter((s) => s.status === "completed").length,
      active: sessions.filter((s) => s.status === "active").length,
      avgScore: (() => {
        const scored = sessions.filter((s) => s.overall_score != null);
        if (scored.length === 0) return null;
        return Math.round(
          scored.reduce((sum, s) => sum + (s.overall_score ?? 0), 0) / scored.length,
        );
      })(),
    }),
    [sessions],
  );

  return (
    <div className="page-shell anim-rise">
      <div className="page-header">
        <div className="flex items-start gap-3">
          <span className="icon-badge icon-badge-brand">
            <BarChart3 size={18} strokeWidth={1.75} />
          </span>
          <div>
            <p className="page-eyebrow">History</p>
            <h1 className="page-title">面试记录</h1>
            <p className="page-desc">回顾每一次模拟面试与报告</p>
          </div>
        </div>
      </div>

      {loading ? (
        <div className="flex items-center justify-center gap-2 py-16 text-[13px] text-ink-muted">
          <span className="block h-4 w-4 anim-spin rounded-full border-2 border-current border-t-transparent" />
          加载记录…
        </div>
      ) : loadError ? (
        <LoadError message={loadError} onRetry={load} />
      ) : (
        <div className="grid grid-cols-1 items-start gap-5 xl:grid-cols-[minmax(0,1fr)_300px]">
          <div className="surface-card overflow-hidden">
            <div className="flex items-center justify-between border-b border-surface-border px-4 py-3">
              <h2 className="text-[13px] font-semibold tracking-tight text-ink">全部场次</h2>
              <span className="chip chip-gray">{stats.total} 场</span>
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
                        onClick={() => setSelectedId(s.id)}
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
        </div>
      )}
    </div>
  );
}

function StatCell({
  value,
  label,
  tone,
}: {
  value: string | number;
  label: string;
  tone?: "success" | "info";
}) {
  const color =
    tone === "success"
      ? "text-[var(--success)]"
      : tone === "info"
        ? "text-[var(--primary)]"
        : "text-ink";
  return (
    <div className="kpi-card !p-3">
      <p className={`kpi-value !text-xl ${color}`}>{value}</p>
      <p className="kpi-label mt-1">{label}</p>
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const config = {
    completed: { icon: CheckCircle2, text: "已完成", className: "chip-green" },
    active: { icon: Clock, text: "进行中", className: "chip-blue" },
    pending: { icon: Circle, text: "待开始", className: "chip-gray" },
  };
  const c = config[status as keyof typeof config] || config.pending;
  const Icon = c.icon;
  return (
    <span className={`chip ${c.className}`}>
      <Icon size={11} />
      {c.text}
    </span>
  );
}

function DetailRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-3">
      <span className="shrink-0 pt-0.5 text-[10px] uppercase tracking-[0.08em] text-ink-subtle">
        {label}
      </span>
      <span className="text-right text-[13px] font-medium text-ink">{value}</span>
    </div>
  );
}

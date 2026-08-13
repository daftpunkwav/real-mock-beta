"use client";

import { useEffect, useState, useMemo, useCallback } from "react";
import Link from "next/link";
import { interviewService as api } from "@/lib/api/interviewService";
import type { GrowthRecord } from "@/types";
import {
  TrendingUp,
  Target,
  Award,
  Play,
  BarChart3,
  Calendar,
  ListTodo,
  AlertCircle,
} from "lucide-react";
import { LoadError } from "@/components/LoadError";

type SystemInsights = Awaited<ReturnType<typeof api.getSystemInsights>>;

export default function GrowthPage() {
  const [records, setRecords] = useState<GrowthRecord[]>([]);
  const [insights, setInsights] = useState<SystemInsights | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const [list, sys] = await Promise.all([
        api.getGrowthHistory(),
        api.getSystemInsights().catch(() => null),
      ]);
      setRecords(list);
      setInsights(sys);
      setSelectedId(list[0]?.id ?? null);
    } catch (e) {
      setLoadError(e instanceof Error ? e.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const allWeaknesses = records.flatMap((r) => r.weak_skills);
  const weaknessCount: Record<string, number> = {};
  allWeaknesses.forEach((w) => {
    weaknessCount[w] = (weaknessCount[w] || 0) + 1;
  });
  const topWeaknesses = Object.entries(weaknessCount)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 5);

  const totalInterviews = records.length;
  const totalPlans = records.reduce((sum, r) => sum + r.training_plan.length, 0);
  const totalWeakSkills = new Set(allWeaknesses).size;

  const selected = useMemo(
    () => records.find((r) => r.id === selectedId) ?? null,
    [records, selectedId],
  );

  const growthPct = Math.min(100, totalInterviews * 25 + Math.min(totalPlans, 4) * 5);
  const growthLevel =
    totalInterviews === 0
      ? "待启动"
      : totalInterviews < 3
        ? "起步阶段"
        : totalInterviews < 6
          ? "持续成长"
          : "进阶提升";

  return (
    <div className="page-shell anim-rise">
      <div className="page-header">
        <div className="flex items-start gap-3">
          <span className="icon-badge icon-badge-warning">
            <TrendingUp size={18} strokeWidth={1.75} />
          </span>
          <div>
            <p className="page-eyebrow">Growth</p>
            <h1 className="page-title">成长追踪</h1>
            <p className="page-desc">识别薄弱项,生成个性化训练计划。</p>
          </div>
        </div>
      </div>

      {loading ? (
        <div className="flex items-center justify-center gap-2 py-16 text-[13px] text-ink-muted">
          <span className="block h-4 w-4 anim-spin rounded-full border-2 border-current border-t-transparent" />
          加载中…
        </div>
      ) : loadError ? (
        <LoadError message={loadError} onRetry={load} />
      ) : (
        <div className="grid grid-cols-1 items-start gap-5 xl:grid-cols-[minmax(0,1fr)_300px]">
          <div className="min-w-0 space-y-4">
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

            {insights && (
              <Section title="系统自我成长" icon={BarChart3}>
                <p className="mb-3 text-[11px] leading-relaxed text-ink-subtle">
                  跨面试聚合:公司分布、工具调用、薄弱点沉淀。
                  {insights.interview_tools_enabled ? " 工具循环已开启。" : " 工具循环已关闭。"}
                  {insights.github_token_configured
                    ? " GitHub Token 已配置。"
                    : " 未配置 GITHUB_TOKEN。"}
                </p>
                <div className="mb-3 grid grid-cols-2 gap-2">
                  {Object.entries(insights.company_session_counts || {})
                    .slice(0, 6)
                    .map(([k, v]) => (
                      <div
                        key={k}
                        className="kpi-card flex !flex-row items-center justify-between gap-2 !p-2.5"
                      >
                        <span className="truncate text-[11px] text-ink-muted">{k}</span>
                        <span className="font-mono text-[12px] font-semibold text-ink num-tabular">
                          {v} 场
                        </span>
                      </div>
                    ))}
                </div>
                {insights.recent_probes && insights.recent_probes.length > 0 && (
                  <div>
                    <p className="mb-1.5 text-[10px] font-semibold uppercase tracking-[0.08em] text-ink-subtle">
                      近期线索
                    </p>
                    <ul className="max-h-32 space-y-2 overflow-y-auto text-[11px] leading-relaxed text-ink-muted">
                      {insights.recent_probes.slice(0, 5).map((p, i) => (
                        <li key={i} className="break-words">
                          · [{p.company || "—"}] {p.point}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </Section>
            )}

            <Section title="训练历史" icon={Award}>
              {records.length > 0 ? (
                <div className="space-y-2">
                  {records.map((r) => {
                    const active = selectedId === r.id;
                    return (
                      <button
                        key={r.id}
                        type="button"
                        onClick={() => setSelectedId(r.id)}
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
          </div>

          <aside className="space-y-3 xl:sticky xl:top-6">
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
          </aside>
        </div>
      )}
    </div>
  );
}

function Section({
  title,
  icon: Icon,
  children,
}: {
  title: string;
  icon: React.ComponentType<{ size?: number; className?: string; strokeWidth?: number }>;
  children: React.ReactNode;
}) {
  return (
    <section className="surface-card overflow-hidden">
      <header className="flex items-center gap-2.5 border-b border-surface-border bg-surface-alt px-5 py-3.5">
        <span className="icon-badge icon-badge-brand">
          <Icon size={15} strokeWidth={1.75} />
        </span>
        <h2 className="text-[14px] font-semibold tracking-tight text-ink">{title}</h2>
      </header>
      <div className="p-5">{children}</div>
    </section>
  );
}

function PreviewRow({
  icon: Icon,
  label,
  value,
}: {
  icon: React.ComponentType<{ size?: number; className?: string; strokeWidth?: number }>;
  label: string;
  value: string;
}) {
  return (
    <div className="flex items-start gap-2.5">
      <Icon size={13} className="mt-0.5 shrink-0 text-ink-subtle" strokeWidth={1.75} />
      <div className="min-w-0">
        <p className="text-[10px] uppercase leading-none tracking-[0.08em] text-ink-subtle">
          {label}
        </p>
        <p className="mt-1 text-[13px] font-medium text-ink">{value}</p>
      </div>
    </div>
  );
}

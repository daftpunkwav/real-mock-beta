"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { interviewService as api } from "@/lib/api/interviewService";
import type { InterviewReport, ScoreBreakdown } from "@/types";
import { ArrowLeft, RefreshCw, FileBarChart } from "lucide-react";

export default function ReportPage() {
  const params = useParams();
  const sessionId = Number(params.id);
  const [report, setReport] = useState<InterviewReport | null>(null);
  const [duration, setDuration] = useState<number | undefined>();
  const [messagesCount, setMessagesCount] = useState<number | undefined>();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const applyPayload = (data: {
    report: InterviewReport;
    duration_minutes?: number;
    messages_count?: number;
  }) => {
    setReport(data.report);
    setDuration(data.duration_minutes);
    setMessagesCount(data.messages_count);
  };

  const loadReport = () => {
    setLoading(true);
    setError("");
    api
      .getReport(sessionId)
      .then(applyPayload)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    if (!Number.isFinite(sessionId) || sessionId <= 0) {
      setError("无效的会话 ID");
      setLoading(false);
      return;
    }
    let cancelled = false;

    api
      .getReport(sessionId)
      .then((data) => {
        if (cancelled) return;
        applyPayload(data);
        setError("");
        setLoading(false);
      })
      .catch((e) => {
        if (cancelled) return;
        const msg = e instanceof Error ? e.message : String(e);
        const missing =
          /尚未|不存在|404|生成/.test(msg) ||
          (e && typeof e === "object" && "status" in e && Number(e.status) === 404);
        if (missing) {
          setError("报告尚未生成。可点击下方按钮生成或重新加载。");
        } else {
          setError(msg);
        }
        setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [sessionId]);

  if (loading) {
    return (
      <div className="page-shell-tight flex min-h-[40vh] items-center justify-center gap-2 text-[13px] text-ink-muted">
        <span className="block h-4 w-4 anim-spin rounded-full border-2 border-current border-t-transparent" />
        生成报告中…
      </div>
    );
  }

  if (error || !report) {
    return (
      <div className="page-shell-tight py-16 text-center">
        <p className="mb-4 text-[13px] text-ink-muted">{error || "报告不可用"}</p>
        <div className="flex flex-wrap justify-center gap-2.5">
          <button
            type="button"
            className="btn-secondary"
            onClick={() => {
              setLoading(true);
              api
                .finishInterview(sessionId)
                .catch(() => undefined)
                .finally(() => loadReport());
            }}
          >
            <RefreshCw size={13} /> 生成 / 重新加载
          </button>
          <Link href="/interview" className="btn-primary">
            返回面试
          </Link>
        </div>
      </div>
    );
  }

  const scores = normalizeScores(report.score_breakdown);
  const shortSession =
    (typeof messagesCount === "number" && messagesCount < 6) ||
    (typeof duration === "number" && duration < 5);

  return (
    <div className="page-shell-tight anim-rise">
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
            style={{ color: scoreColor(report.overall_score) }}
          >
            {formatScore(report.overall_score)}
          </div>
          <div className="mt-1 text-[10px] font-semibold uppercase tracking-[0.1em] text-ink-subtle">
            综合评分 / 100
          </div>
        </div>
      </div>

      {shortSession && (
        <div className="alert alert-warning mb-6">
          本场对话较短或有效作答很少,维度分可能偏低或接近 0,属评估结果而非页面缺数。
        </div>
      )}

      <div className="mb-6 grid grid-cols-2 gap-2.5 sm:grid-cols-3 lg:grid-cols-6">
        {[
          { label: "技术能力", score: scores.technical },
          { label: "表达能力", score: scores.communication },
          { label: "项目深度", score: scores.project_depth },
          { label: "问题解决", score: scores.problem_solving },
          { label: "临场状态", score: scores.presence },
          { label: "话轮礼貌", score: scores.politeness },
        ].map((item) => {
          const display = formatScore(item.score);
          const scoreVal = typeof item.score === "number" ? item.score : null;
          const numeric = scoreVal != null;
          return (
            <div
              key={item.label}
              className="kpi-card items-center text-center !p-3"
            >
              <div
                className="font-mono text-[24px] font-semibold leading-none num-tabular"
                style={{ color: numeric ? scoreColor(scoreVal) : undefined }}
              >
                {display}
              </div>
              <div className="kpi-label mt-2 text-center">{item.label}</div>
              {numeric && scoreVal != null && (
                <div className="mt-2 h-1 w-full overflow-hidden rounded-full bg-surface-muted">
                  <div
                    className="h-full rounded-full transition-all"
                    style={{
                      width: `${Math.min(100, Math.max(0, scoreVal))}%`,
                      backgroundColor: scoreColor(scoreVal),
                    }}
                  />
                </div>
              )}
            </div>
          );
        })}
      </div>

      <RadarChart scores={scores} />

      <Section title="优势" items={report.strengths} tone="success" />
      <Section title="不足" items={report.weaknesses} tone="danger" />
      <Section title="简历改进建议" items={report.resume_suggestions || []} tone="brand" />
      <Section title="面试表现建议" items={report.interview_suggestions || []} tone="brand" />
      <Section title="综合建议" items={report.improvement_suggestions} tone="brand" />
      <Section title="下一阶段训练计划" items={report.training_plan} tone="warning" />

      {report.presence_moments && report.presence_moments.length > 0 && (
        <Section title="临场关键时刻" items={report.presence_moments} tone="brand" />
      )}

      {report.face_analysis_summary && (
        <div className="surface-card mt-5 p-4">
          <h3 className="mb-2 text-[13px] font-semibold tracking-tight text-ink">
            面试状态分析
          </h3>
          <p className="text-[12.5px] leading-relaxed text-ink-muted">
            {report.face_analysis_summary}
          </p>
        </div>
      )}

      <div className="mt-7 flex flex-wrap gap-2.5">
        <Link href="/interview" className="btn-primary">
          <RefreshCw size={13} /> 再来一次
        </Link>
        <Link href="/growth" className="btn-secondary">
          查看成长记录
        </Link>
      </div>
    </div>
  );
}

/** 保证雷达/卡片拿到完整数值字段;缺省为 null(显示 —),0 视为有效分。 */
function normalizeScores(raw: ScoreBreakdown | undefined | null): {
  technical: number | null;
  communication: number | null;
  project_depth: number | null;
  problem_solving: number | null;
  presence: number | null;
  politeness: number | null;
  overall: number | null;
} {
  const pick = (v: unknown): number | null =>
    typeof v === "number" && Number.isFinite(v) ? Math.round(v) : null;
  return {
    technical: pick(raw?.technical),
    communication: pick(raw?.communication),
    project_depth: pick(raw?.project_depth),
    problem_solving: pick(raw?.problem_solving),
    presence: pick(raw?.presence),
    politeness: pick(raw?.politeness),
    overall: pick(raw?.overall),
  };
}

function formatScore(score: number | null | undefined): string {
  if (typeof score !== "number" || !Number.isFinite(score)) return "—";
  return String(Math.round(score));
}

function RadarChart({
  scores,
}: {
  scores: ReturnType<typeof normalizeScores>;
}) {
  const dims = [
    { key: "technical" as const, label: "技术" },
    { key: "communication" as const, label: "表达" },
    { key: "project_depth" as const, label: "项目" },
    { key: "problem_solving" as const, label: "解题" },
    { key: "presence" as const, label: "临场" },
    { key: "politeness" as const, label: "礼貌" },
  ];
  const cx = 120;
  const cy = 120;
  const r = 80;
  const values = dims.map((d) => {
    const v = scores[d.key];
    return typeof v === "number" ? Math.min(1, Math.max(0, v / 100)) : 0;
  });
  const points = dims
    .map((_, i) => {
      const angle = (Math.PI * 2 * i) / dims.length - Math.PI / 2;
      const v = values[i] ?? 0;
      return `${cx + Math.cos(angle) * r * v},${cy + Math.sin(angle) * r * v}`;
    })
    .join(" ");
  const rings = [0.25, 0.5, 0.75, 1];
  const hasAny = values.some((v) => v > 0);

  return (
    <div className="surface-card mb-6 p-4">
      <h3 className="mb-1 text-center text-[14px] font-semibold tracking-tight text-ink">
        能力雷达图
      </h3>
      <p className="mb-4 text-center text-[11px] text-ink-subtle">各轴满分 100;0 分会落在中心附近</p>
      <div className="flex justify-center">
        <svg width="240" height="240" viewBox="0 0 240 240" aria-label="能力雷达图">
          {rings.map((ring) => (
            <polygon
              key={ring}
              points={dims
                .map((_, i) => {
                  const angle = (Math.PI * 2 * i) / dims.length - Math.PI / 2;
                  return `${cx + Math.cos(angle) * r * ring},${cy + Math.sin(angle) * r * ring}`;
                })
                .join(" ")}
              fill="none"
              stroke="var(--border)"
              strokeWidth="1"
            />
          ))}
          {dims.map((d, i) => {
            const angle = (Math.PI * 2 * i) / dims.length - Math.PI / 2;
            const x = cx + Math.cos(angle) * (r + 18);
            const y = cy + Math.sin(angle) * (r + 18);
            const score = scores[d.key];
            return (
              <text
                key={d.key}
                x={x}
                y={y}
                textAnchor="middle"
                dominantBaseline="middle"
                className="fill-ink-subtle"
                style={{ fontSize: 10 }}
              >
                {d.label}
                {typeof score === "number" ? ` ${score}` : ""}
              </text>
            );
          })}
          {hasAny && (
            <polygon
              points={points}
              fill="color-mix(in srgb, var(--primary) 28%, transparent)"
              stroke="var(--primary)"
              strokeWidth="2"
            />
          )}
          {!hasAny && (
            <text
              x={cx}
              y={cy}
              textAnchor="middle"
              dominantBaseline="middle"
              className="fill-ink-subtle"
              style={{ fontSize: 11 }}
            >
              暂无有效维度分
            </text>
          )}
        </svg>
      </div>
    </div>
  );
}

function scoreColor(score: number | null | undefined): string {
  if (score == null || Number.isNaN(score)) return "var(--muted-foreground)";
  if (score >= 85) return "var(--success)";
  if (score >= 70) return "var(--primary)";
  if (score >= 60) return "var(--warning)";
  return "var(--danger)";
}

function Section({
  title,
  items,
  tone,
}: {
  title: string;
  items: string[];
  tone: "brand" | "success" | "danger" | "warning";
}) {
  if (!items.length) return null;
  const tintMap: Record<string, { bg: string; fg: string; border: string }> = {
    success: {
      bg: "var(--success-soft)",
      fg: "var(--success-ink)",
      border: "color-mix(in srgb, var(--success) 22%, transparent)",
    },
    danger: {
      bg: "var(--danger-soft)",
      fg: "var(--danger-ink)",
      border: "color-mix(in srgb, var(--danger) 22%, transparent)",
    },
    brand: {
      bg: "var(--info-soft)",
      fg: "var(--info-ink)",
      border: "color-mix(in srgb, var(--primary) 22%, transparent)",
    },
    warning: {
      bg: "var(--warning-soft)",
      fg: "var(--warning-ink)",
      border: "color-mix(in srgb, var(--warning) 28%, transparent)",
    },
  };
  const t = tintMap[tone] ?? tintMap.brand!;
  return (
    <div
      className="mt-4 rounded-md border p-4"
      style={{ background: t.bg, borderColor: t.border }}
    >
      <h3
        className="mb-2 text-[12px] font-semibold uppercase tracking-[0.08em]"
        style={{ color: t.fg }}
      >
        {title}
      </h3>
      <ul className="space-y-1.5">
        {items.map((item, i) => (
          <li key={i} className="flex items-start gap-2 text-[13px] leading-relaxed text-ink">
            <span className="mt-1 inline-block h-1 w-1 shrink-0 rounded-full bg-current opacity-50" />
            <span className="min-w-0 break-words">{item}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

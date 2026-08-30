"use client";

import { useMemo, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import {
  AlertTriangle,
  Briefcase,
  Compass,
  LayoutList,
  Lightbulb,
} from "lucide-react";
import type { Resume, ResumeAnalysis } from "@/types";
import { normalizeCnPunctuation, parseRewriteExample } from "@/lib/cnText";
import { EvalRichText } from "./EvalRichText";
import { RadarChart } from "./RadarChart";
import { ScoreRing } from "./ScoreRing";
import {
  FirstImpressionCard,
  HeadlineBanner,
  InterviewerNotes,
  PercentileBar,
} from "./ImpressionCards";
import {
  CareerPanel,
  CompanyFitBars,
  ProjectCards,
  SectionHeatmap,
  SkillTrustBoard,
} from "./DeepDiveCards";

const DIM_LABELS: Record<string, string> = {
  structure_clarity: "结构清晰度",
  visual_layout: "版式布局",
  typography: "字体可读性",
  impact_quantification: "成果量化",
  tech_depth: "技术深度",
  project_narrative: "项目叙事",
  role_fit: "岗位匹配",
  keyword_ats: "ATS 关键词",
  credibility: "可信度",
  seniority_signal: "职级信号",
  growth_signal: "成长潜力",
  collaboration_signal: "协作信号",
};

export function asAnalysis(raw: Resume["analysis"]): ResumeAnalysis | null {
  if (!raw || typeof raw !== "object") return null;
  if (!("score" in raw)) return null;
  return raw as ResumeAnalysis;
}

function dimScore(
  v: ResumeAnalysis["dimension_scores"] extends infer D
    ? D extends Record<string, infer V>
      ? V
      : never
    : never,
): number {
  if (typeof v === "number") return v;
  if (v && typeof v === "object" && "score" in v) return Number((v as { score: number }).score) || 0;
  return 0;
}

function dimComment(
  v: ResumeAnalysis["dimension_scores"] extends infer D
    ? D extends Record<string, infer V>
      ? V
      : never
    : never,
): string {
  if (v && typeof v === "object" && "comment" in v) {
    return String((v as { comment?: string }).comment || "").trim();
  }
  return "";
}

type TabId = "overview" | "projects" | "skills" | "actions";

/** 深度评价 · 审阅笺(标签页组织) */
export function AnalysisPanel({ analysis }: { analysis: ResumeAnalysis }) {
  const dims = analysis.dimension_scores || {};
  const dimEntries = Object.entries(dims);
  const radarDims = dimEntries.map(([key, v]) => ({
    key,
    label: DIM_LABELS[key] || key,
    score: dimScore(v as never),
  }));
  const percentile =
    typeof analysis.benchmark_percentile === "number" ? analysis.benchmark_percentile : null;

  // 内容齐备的标签页才显示;深度字段缺失时自动收敛为单页
  const tabs = useMemo(() => {
    const list: Array<{ id: TabId; label: string; icon: React.ReactNode }> = [
      { id: "overview", label: "总览", icon: <LayoutList size={13} /> },
    ];
    const hasProjects =
      (analysis.project_cards?.length ?? 0) > 0 ||
      (analysis.project_deep_dive?.length ?? 0) > 0 ||
      (analysis.rewrite_examples?.length ?? 0) > 0 ||
      (analysis.predicted_questions?.length ?? 0) > 0;
    const hasSkills =
      analysis.skill_trust != null ||
      (analysis.section_reviews?.length ?? 0) > 0 ||
      analysis.career_analysis != null ||
      !!analysis.salary_positioning;
    const hasActions =
      !!analysis.layout_review ||
      !!analysis.typography_review ||
      !!analysis.content_review ||
      (analysis.red_flags?.length ?? 0) > 0 ||
      (analysis.improvement_suggestions?.length ?? 0) > 0 ||
      (analysis.market_insights?.length ?? 0) > 0 ||
      (analysis.company_fit?.length ?? 0) > 0 ||
      (analysis.ats_keywords?.length ?? 0) > 0 ||
      (analysis.missing_keywords?.length ?? 0) > 0 ||
      (analysis.interview_risk_areas?.length ?? 0) > 0;
    if (hasProjects) list.push({ id: "projects", label: "项目深挖", icon: <Briefcase size={13} /> });
    if (hasSkills) list.push({ id: "skills", label: "技能职涯", icon: <Compass size={13} /> });
    if (hasActions) list.push({ id: "actions", label: "行动市场", icon: <Lightbulb size={13} /> });
    return list;
  }, [analysis]);

  const [tab, setTab] = useState<TabId>("overview");
  const activeTab = tabs.some((x) => x.id === tab) ? tab : "overview";

  return (
    <article className="eval-sheet">
      <header className="eval-masthead">
        <div className="min-w-0">
          <h2 className="eval-masthead-title">Agent 深度评价</h2>
          <p className="eval-masthead-sub">简历审阅意见</p>
        </div>
        <ScoreRing score={analysis.score} />
      </header>

      {analysis.headline?.trim() && <HeadlineBanner text={analysis.headline} />}

      {analysis.first_impression?.trim() && (
        <FirstImpressionCard text={analysis.first_impression} />
      )}

      {/* 标签栏 */}
      {tabs.length > 1 && (
        <div className="eval-tabs" role="tablist" aria-label="评价分区">
          {tabs.map((x) => (
            <button
              key={x.id}
              type="button"
              role="tab"
              aria-selected={activeTab === x.id}
              onClick={() => setTab(x.id)}
              className={`eval-tab ${activeTab === x.id ? "is-active" : ""}`}
            >
              {x.icon}
              {x.label}
              {activeTab === x.id && (
                <motion.span
                  layoutId="eval-tab-underline"
                  className="eval-tab-underline"
                  transition={{ type: "spring", stiffness: 420, damping: 34 }}
                />
              )}
            </button>
          ))}
        </div>
      )}

      <AnimatePresence mode="wait">
        <motion.div
          key={activeTab}
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -6 }}
          transition={{ duration: 0.2 }}
          className="eval-tabpanel"
        >
          {activeTab === "overview" && (
            <OverviewTab analysis={analysis} dimEntries={dimEntries} radarDims={radarDims} percentile={percentile} />
          )}
          {activeTab === "projects" && <ProjectsTab analysis={analysis} />}
          {activeTab === "skills" && <SkillsTab analysis={analysis} />}
          {activeTab === "actions" && <ActionsTab analysis={analysis} />}
        </motion.div>
      </AnimatePresence>
    </article>
  );
}

type DimEntry = [string, ResumeAnalysis["dimension_scores"] extends infer D ? (D extends Record<string, infer V> ? V : never) : never];

function OverviewTab({
  analysis,
  dimEntries,
  radarDims,
  percentile,
}: {
  analysis: ResumeAnalysis;
  dimEntries: DimEntry[];
  radarDims: Array<{ key: string; label: string; score: number }>;
  percentile: number | null;
}) {
  const t = normalizeCnPunctuation;
  return (
    <>
      {analysis.overall_narrative && (
        <section className="eval-section">
          <span className="eval-label">总评</span>
          <p className="eval-prose">
            <EvalRichText text={t(analysis.overall_narrative)} />
          </p>
          {analysis.seniority_estimate && (
            <p className="eval-meta">
              职级判断 · <strong>{t(analysis.seniority_estimate)}</strong>
            </p>
          )}
        </section>
      )}

      {analysis.role_fit_summary && (
        <section className="eval-callout">
          <span className="eval-label">岗位匹配</span>
          <p className="eval-prose eval-prose-sm">
            <EvalRichText text={t(analysis.role_fit_summary)} />
          </p>
        </section>
      )}

      {radarDims.length >= 3 && (
        <section className="eval-section">
          <span className="eval-label">能力雷达</span>
          <div className="eval-radar-grid">
            <RadarChart dims={radarDims} />
            <div className="eval-dim-grid eval-dim-grid-compact">
              {dimEntries.map(([k, v]) => {
                const sc = dimScore(v as never);
                const comment = dimComment(v as never);
                return (
                  <div key={k} className="min-w-0">
                    <div className="flex items-baseline justify-between gap-3 mb-1.5">
                      <span className="eval-dim-name">{DIM_LABELS[k] || k}</span>
                      <span className="eval-dim-score">{sc}</span>
                    </div>
                    <div className="progress !h-1">
                      <div
                        className="progress-bar"
                        style={{ width: `${Math.min(sc, 100)}%` }}
                      />
                    </div>
                    {comment ? (
                      <p className="eval-dim-comment">
                        <EvalRichText text={t(comment)} />
                      </p>
                    ) : null}
                  </div>
                );
              })}
            </div>
          </div>
        </section>
      )}

      {percentile != null && <PercentileBar pct={percentile} />}

      {analysis.interviewer_comments && analysis.interviewer_comments.length > 0 && (
        <InterviewerNotes items={analysis.interviewer_comments} />
      )}
    </>
  );
}

function ProjectsTab({ analysis }: { analysis: ResumeAnalysis }) {
  const t = normalizeCnPunctuation;
  return (
    <>
      {analysis.project_cards && analysis.project_cards.length > 0 && (
        <ProjectCards cards={analysis.project_cards} />
      )}

      {analysis.project_deep_dive && analysis.project_deep_dive.length > 0 && (
        <EvalNumberedStack
          title="项目深挖点"
          prefix="P"
          items={analysis.project_deep_dive.map(t)}
        />
      )}

      {analysis.rewrite_examples && analysis.rewrite_examples.length > 0 && (
        <RewriteGallery items={analysis.rewrite_examples} />
      )}

      {analysis.predicted_questions && analysis.predicted_questions.length > 0 && (
        <EvalNumberedStack
          title="预测面试题"
          prefix="Q"
          items={analysis.predicted_questions.map(t)}
        />
      )}
    </>
  );
}

function SkillsTab({ analysis }: { analysis: ResumeAnalysis }) {
  const t = normalizeCnPunctuation;
  return (
    <>
      {analysis.section_reviews && analysis.section_reviews.length > 0 && (
        <SectionHeatmap reviews={analysis.section_reviews} />
      )}

      {analysis.skill_trust && <SkillTrustBoard trust={analysis.skill_trust} />}

      {analysis.career_analysis && <CareerPanel career={analysis.career_analysis} />}

      {analysis.salary_positioning?.trim() && (
        <section className="eval-callout">
          <span className="eval-label">薪资定位参考</span>
          <p className="eval-prose eval-prose-sm">
            <EvalRichText text={t(analysis.salary_positioning)} />
          </p>
        </section>
      )}
    </>
  );
}

function ActionsTab({ analysis }: { analysis: ResumeAnalysis }) {
  const t = normalizeCnPunctuation;
  return (
    <>
      {(analysis.layout_review || analysis.typography_review || analysis.content_review) && (
        <div className="flex flex-col gap-6">
          {analysis.layout_review && (
            <section className="eval-section">
              <span className="eval-label">排版与结构</span>
              <p className="eval-prose eval-prose-sm">
                <EvalRichText text={t(analysis.layout_review)} />
              </p>
            </section>
          )}
          {analysis.typography_review && (
            <section className="eval-section">
              <span className="eval-label">字体与可读性</span>
              <p className="eval-prose eval-prose-sm">
                <EvalRichText text={t(analysis.typography_review)} />
              </p>
            </section>
          )}
          {analysis.content_review && (
            <section className="eval-section">
              <span className="eval-label">内容深度</span>
              <p className="eval-prose eval-prose-sm">
                <EvalRichText text={t(analysis.content_review)} />
              </p>
            </section>
          )}
        </div>
      )}

      <div className="eval-pair">
        {analysis.strengths && analysis.strengths.length > 0 && (
          <EvalList title="优势" items={analysis.strengths.map(t)} />
        )}
        {analysis.weaknesses && analysis.weaknesses.length > 0 && (
          <EvalList title="不足" items={analysis.weaknesses.map(t)} />
        )}
      </div>

      {analysis.red_flags && analysis.red_flags.length > 0 && (
        <div className="alert alert-error !py-4">
          <AlertTriangle size={16} className="shrink-0 mt-0.5" />
          <div className="min-w-0">
            <p className="font-semibold text-sm mb-2.5 tracking-[0.06em]">风险点</p>
            <ul className="eval-list">
              {analysis.red_flags.map((s, i) => (
                <li key={i}>
                  <span className="eval-list-mark">·</span>
                  <span className="eval-list-body">
                    <EvalRichText text={t(s)} />
                  </span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}

      <div className="eval-pair">
        {analysis.improvement_suggestions && analysis.improvement_suggestions.length > 0 && (
          <EvalList title="改进建议" items={analysis.improvement_suggestions.map(t)} />
        )}
        {analysis.interview_risk_areas && analysis.interview_risk_areas.length > 0 && (
          <EvalList title="面试易被打穿" items={analysis.interview_risk_areas.map(t)} />
        )}
      </div>

      {analysis.company_fit && analysis.company_fit.length > 0 && (
        <CompanyFitBars fits={analysis.company_fit} />
      )}

      {analysis.market_insights && analysis.market_insights.length > 0 && (
        <EvalList title="市场参考" items={analysis.market_insights.map(t)} />
      )}

      {(analysis.ats_keywords?.length || analysis.missing_keywords?.length) ? (
        <div className="eval-kw-grid">
          {!!analysis.ats_keywords?.length && (
            <section className="eval-section min-w-0">
              <span className="eval-label">已覆盖关键词</span>
              <div className="eval-kw is-covered">
                {analysis.ats_keywords.map((k) => (
                  <span key={k}>{k}</span>
                ))}
              </div>
            </section>
          )}
          {!!analysis.missing_keywords?.length && (
            <section className="eval-section min-w-0">
              <span className="eval-label">建议补充</span>
              <ul className="eval-kw-suggest">
                {analysis.missing_keywords.map((k) => (
                  <li key={k}>
                    <EvalRichText text={t(k)} />
                  </li>
                ))}
              </ul>
            </section>
          )}
        </div>
      ) : null}
    </>
  );
}

function EvalNumberedStack({
  title,
  items,
  prefix,
}: {
  title: string;
  items: string[];
  prefix: string;
}) {
  return (
    <section className="eval-section">
      <span className="eval-label">{title}</span>
      <div className="eval-q-stack">
        {items.map((q, i) => (
          <div key={i} className="eval-q">
            <span className="eval-q-idx">
              {prefix}
              {i + 1}
            </span>
            <p className="eval-prose eval-prose-sm !max-w-none m-0">
              <EvalRichText text={q} />
            </p>
          </div>
        ))}
      </div>
    </section>
  );
}

function RewriteGallery({
  items,
}: {
  items: NonNullable<ResumeAnalysis["rewrite_examples"]>;
}) {
  const pairs = items
    .map((item) => parseRewriteExample(item))
    .filter((p): p is { before: string; after: string } => Boolean(p));

  if (pairs.length === 0) {
    // 无法解析时降级为普通列表，避免再露出 {'before': ...}
    const fallback = items
      .map((item) => {
        if (typeof item === "string") return normalizeCnPunctuation(item);
        if (item && typeof item === "object") {
          const b = "before" in item ? String(item.before || "") : "";
          const a = "after" in item ? String(item.after || "") : "";
          if (b && a) return null;
          return normalizeCnPunctuation(JSON.stringify(item));
        }
        return null;
      })
      .filter((x): x is string => Boolean(x));
    if (!fallback.length) return null;
    return <EvalList title="改写示例" items={fallback} />;
  }

  return (
    <section className="eval-section">
      <span className="eval-label">改写示例</span>
      <div className="eval-rewrite-stack">
        {pairs.map((pair, i) => (
          <article key={i} className="eval-rewrite-card">
            <div className="eval-rewrite-block is-before">
              <div className="eval-rewrite-meta">
                <span className="eval-rewrite-idx">{String(i + 1).padStart(2, "0")}</span>
                <span className="eval-rewrite-tag">改前</span>
              </div>
              <p className="eval-rewrite-text">
                <EvalRichText text={normalizeCnPunctuation(pair.before)} />
              </p>
            </div>
            <div className="eval-rewrite-block is-after">
              <div className="eval-rewrite-meta">
                <span className="eval-rewrite-tag">改后</span>
              </div>
              <p className="eval-rewrite-text">
                <EvalRichText text={normalizeCnPunctuation(pair.after)} />
              </p>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}

function EvalList({ title, items }: { title: string; items: string[] }) {
  return (
    <section className="eval-section min-w-0">
      <span className="eval-label">{title}</span>
      <ul className="eval-list">
        {items.map((s, i) => (
          <li key={i}>
            <span className="eval-list-mark">·</span>
            <span className="eval-list-body">
              <EvalRichText text={s} />
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}

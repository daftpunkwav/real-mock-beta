"use client";

import { useMemo, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Briefcase, Compass, LayoutList, Lightbulb } from "lucide-react";
import type { ResumeAnalysis } from "@/types";
import { ScoreRing } from "./ScoreRing";
import { FirstImpressionCard, HeadlineBanner } from "./ImpressionCards";
import { DIM_LABELS, dimScore, type DimEntry, type TabId } from "../analysisFormat";
import { OverviewTab } from "./OverviewTab";
import { ProjectsTab } from "./ProjectsTab";
import { SkillsTab } from "./SkillsTab";
import { ActionsTab } from "./ActionsTab";

/** 深度评价 · 审阅笺(标签页组织) */
export function AnalysisPanel({ analysis }: { analysis: ResumeAnalysis }) {
  const dims = analysis.dimension_scores || {};
  const dimEntries: DimEntry[] = Object.entries(dims);
  const radarDims = dimEntries.map(([key, v]) => ({
    key,
    label: DIM_LABELS[key] || key,
    score: dimScore(v),
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

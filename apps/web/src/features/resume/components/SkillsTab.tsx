"use client";

import type { ResumeAnalysis } from "@/types";
import { normalizeCnPunctuation } from "@/lib/cnText";
import { EvalRichText } from "./EvalRichText";
import { CareerPanel, SectionHeatmap, SkillTrustBoard } from "./DeepDiveCards";

export function SkillsTab({ analysis }: { analysis: ResumeAnalysis }) {
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

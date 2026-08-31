"use client";

import type { ResumeAnalysis } from "@/types";
import { normalizeCnPunctuation } from "@/lib/cnText";
import { ProjectCards } from "./ProjectCards";
import { EvalNumberedStack } from "./EvalNumberedStack";
import { RewriteGallery } from "./RewriteGallery";

export function ProjectsTab({ analysis }: { analysis: ResumeAnalysis }) {
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

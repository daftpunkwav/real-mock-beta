"use client";

import { AlertTriangle } from "lucide-react";
import type { ResumeAnalysis } from "@/types";
import { normalizeCnPunctuation } from "@/lib/cnText";
import { EvalRichText } from "./EvalRichText";
import { CompanyFitBars } from "./CompanyFitBars";
import { EvalList } from "./EvalList";

export function ActionsTab({ analysis }: { analysis: ResumeAnalysis }) {
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

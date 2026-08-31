"use client";

import type { ResumeAnalysis } from "@/types";
import { normalizeCnPunctuation } from "@/lib/cnText";
import { EvalRichText } from "./EvalRichText";
import { RadarChart } from "./RadarChart";
import { InterviewerNotes, PercentileBar } from "./ImpressionCards";
import { DIM_LABELS, dimComment, dimScore, type DimEntry } from "../analysisFormat";

export function OverviewTab({
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
                const sc = dimScore(v);
                const comment = dimComment(v);
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

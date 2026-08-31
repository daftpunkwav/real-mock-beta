"use client";

import { GitBranch } from "lucide-react";
import type { CareerAnalysisData } from "@/types";
import { normalizeCnPunctuation } from "@/lib/cnText";
import { EvalRichText } from "./EvalRichText";
import { scoreColor } from "./scoreColor";

const t = normalizeCnPunctuation;

/* ── 职涯轨迹面板 ─────────────────────────────── */

export function CareerPanel({ career }: { career: CareerAnalysisData }) {
  if (!career.trajectory && career.gaps.length === 0) return null;
  const stability = Math.max(0, Math.min(100, career.stability_score));
  const color = scoreColor(stability);

  return (
    <section className="eval-section">
      <span className="eval-label">职涯轨迹分析</span>
      <div className="eval-career">
        <div className="eval-career-side">
          <div
            className="eval-career-gauge"
            style={{ background: `conic-gradient(${color} ${stability * 0.75}%, var(--muted) 0)` }}
            role="img"
            aria-label={`方向专注度 ${stability}`}
          >
            <span className="eval-career-gauge-inner">
              <span className="num-tabular eval-career-gauge-num" style={{ color }}>
                {stability}
              </span>
              <span className="eval-career-gauge-label">专注度</span>
            </span>
          </div>
        </div>
        <div className="min-w-0 flex-1">
          {career.trajectory && (
            <p className="eval-career-trajectory">
              <GitBranch size={13} className="mt-1 shrink-0 text-[var(--primary)]" />
              <span>
                <EvalRichText text={t(career.trajectory)} />
              </span>
            </p>
          )}
          {career.gaps.length > 0 && (
            <div className="eval-career-gaps">
              <p className="eval-career-gaps-label">时间线疑点</p>
              <ul>
                {career.gaps.map((g, i) => (
                  <li key={i}>
                    <EvalRichText text={t(g)} />
                  </li>
                ))}
              </ul>
            </div>
          )}
          {career.notes && (
            <p className="eval-career-notes">{t(career.notes)}</p>
          )}
        </div>
      </div>
    </section>
  );
}

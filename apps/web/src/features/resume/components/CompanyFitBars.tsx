"use client";

import { useRef } from "react";
import { useInView, useReducedMotion } from "framer-motion";
import { Building2 } from "lucide-react";
import type { CompanyFitData } from "@/types";
import { normalizeCnPunctuation } from "@/lib/cnText";
import { EvalRichText } from "./EvalRichText";
import { scoreColor } from "./scoreColor";

const t = normalizeCnPunctuation;

/* ── 公司层级匹配条 ─────────────────────────────── */

function FitBar({ fit, index }: { fit: CompanyFitData; index: number }) {
  const ref = useRef<HTMLDivElement>(null);
  const inView = useInView(ref, { once: true, margin: "-20px" });
  const reduce = useReducedMotion();
  const color = scoreColor(fit.fit_score);

  return (
    <div ref={ref} className="eval-fit-row">
      <div className="eval-fit-head">
        <span className="eval-fit-tier">
          <Building2 size={12} className="shrink-0 text-ink-subtle" />
          {fit.tier}
        </span>
        <span className="eval-fit-score num-tabular" style={{ color }}>
          {fit.fit_score}%
        </span>
      </div>
      <div className="eval-fit-track">
        <div
          className="eval-fit-fill"
          style={{
            width: inView || reduce ? `${fit.fit_score}%` : "0%",
            background: color,
            transitionDelay: `${index * 0.12}s`,
          }}
        />
      </div>
      {fit.reason && (
        <p className="eval-fit-reason">
          <EvalRichText text={t(fit.reason)} />
        </p>
      )}
    </div>
  );
}

export function CompanyFitBars({ fits }: { fits: CompanyFitData[] }) {
  const cleaned = fits.filter((f) => f.tier);
  if (cleaned.length === 0) return null;
  return (
    <section className="eval-section">
      <span className="eval-label">公司层级匹配度</span>
      <div className="eval-fit-stack">
        {cleaned.map((f, i) => (
          <FitBar key={`${f.tier}-${i}`} fit={f} index={i} />
        ))}
      </div>
    </section>
  );
}

"use client";

import { useEffect, useRef, useState } from "react";
import { useInView, useReducedMotion } from "framer-motion";
import { MessagesSquare, Quote, ScanFace } from "lucide-react";
import { normalizeCnPunctuation } from "@/lib/cnText";
import { EvalRichText } from "./EvalRichText";

/** 人设定位横幅:粗竖线 + 大号标语。 */
export function HeadlineBanner({ text }: { text: string }) {
  const t = normalizeCnPunctuation(text.trim());
  if (!t) return null;
  return (
    <div className="flex items-stretch gap-3.5">
      <span className="w-1 shrink-0 rounded-full bg-gradient-to-b from-[var(--primary)] to-[var(--primary)]/25" />
      <div className="min-w-0">
        <p className="text-[10px] font-semibold uppercase tracking-[0.2em] text-ink-subtle">
          一句话人设
        </p>
        <p className="mt-1 text-[17px] font-semibold leading-snug tracking-tight text-ink sm:text-[19px]">
          {t}
        </p>
      </div>
    </div>
  );
}

/** 面试官 30 秒第一印象:纸质感便签 + 大引号。 */
export function FirstImpressionCard({ text }: { text: string }) {
  const t = normalizeCnPunctuation(text.trim());
  if (!t) return null;
  return (
    <div className="eval-impression">
      <Quote size={44} className="eval-impression-quote" aria-hidden />
      <div className="relative min-w-0">
        <p className="mb-2.5 flex items-center gap-2 text-[10px] font-semibold uppercase tracking-[0.2em] text-[var(--primary-ink)]">
          <ScanFace size={13} />
          面试官 30 秒第一印象
        </p>
        <p className="eval-impression-body">
          <EvalRichText text={t} />
        </p>
      </div>
    </div>
  );
}

/** 面试官工位随口点评:交错便签墙,hover 摆正。 */
export function InterviewerNotes({ items }: { items: string[] }) {
  const cleaned = items.map((s) => normalizeCnPunctuation(String(s).trim())).filter(Boolean);
  if (cleaned.length === 0) return null;
  return (
    <section className="eval-section">
      <span className="eval-label">面试官工位随口点评</span>
      <div className="eval-notes-grid">
        {cleaned.map((s, i) => (
          <div key={i} className={`eval-note ${i % 2 === 0 ? "is-tilt-l" : "is-tilt-r"}`}>
            <Quote size={12} className="shrink-0 text-[var(--primary)]" aria-hidden />
            <p className="min-w-0">
              <EvalRichText text={s} />
            </p>
          </div>
        ))}
      </div>
    </section>
  );
}

function percentileColor(pct: number): string {
  if (pct >= 75) return "var(--success)";
  if (pct >= 45) return "var(--primary)";
  if (pct >= 25) return "var(--warning)";
  return "var(--danger)";
}

/** 同岗百分位:渐变轴 + 动画指针。 */
export function PercentileBar({ pct }: { pct: number }) {
  const ref = useRef<HTMLDivElement>(null);
  const inView = useInView(ref, { once: true, margin: "-30px" });
  const reduce = useReducedMotion();
  const [shown, setShown] = useState(false);

  useEffect(() => {
    if (!inView) return;
    if (reduce) {
      setShown(true);
      return;
    }
    const raf = requestAnimationFrame(() => setShown(true));
    return () => cancelAnimationFrame(raf);
  }, [inView, reduce]);

  const clamped = Math.max(0, Math.min(100, Math.round(pct)));
  const color = percentileColor(clamped);

  return (
    <div ref={ref} className="eval-percentile">
      <div className="mb-2.5 flex items-center justify-between gap-3">
        <p className="flex items-center gap-2 text-[10px] font-semibold uppercase tracking-[0.2em] text-ink-subtle">
          <MessagesSquare size={12} />
          同岗竞争力
        </p>
        <p className="text-[12px] text-ink-muted">
          综合实力约超过同方向
          <strong className="mx-1 num-tabular text-[15px]" style={{ color }}>
            {clamped}%
          </strong>
          的候选人
        </p>
      </div>
      <div className="eval-percentile-track">
        <div className="eval-percentile-fill" aria-hidden />
        <span
          className="eval-percentile-pin"
          style={{
            left: `${clamped}%`,
            background: color,
            transform: shown ? "translate(-50%, 0) scale(1)" : "translate(-50%, 0) scale(0)",
          }}
        >
          <span className="eval-percentile-pin-val num-tabular">{clamped}</span>
        </span>
      </div>
      <div className="eval-percentile-scale">
        <span>后 25%</span>
        <span>中位</span>
        <span>前 25%</span>
      </div>
    </div>
  );
}

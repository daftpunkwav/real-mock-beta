"use client";

import { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { BadgeCheck, ChevronDown, CircleAlert, CircleHelp } from "lucide-react";
import type { ProjectCardData } from "@/types";
import { normalizeCnPunctuation } from "@/lib/cnText";
import { EvalRichText } from "./EvalRichText";
import { scoreColor } from "./scoreColor";

const t = normalizeCnPunctuation;

/* ── 项目深挖卡片(手风琴) ─────────────────────────── */

function ProjectCardItem({ card, index }: { card: ProjectCardData; index: number }) {
  const [open, setOpen] = useState(index === 0);
  const color = scoreColor(card.score);

  return (
    <div className={`eval-pcard ${open ? "is-open" : ""}`}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="eval-pcard-head"
        aria-expanded={open}
      >
        <span className="eval-pcard-idx num-tabular">{String(index + 1).padStart(2, "0")}</span>
        <span className="min-w-0 flex-1 text-left">
          <span className="eval-pcard-name">{card.name}</span>
          <span className="eval-pcard-line">{t(card.one_line)}</span>
        </span>
        <span className="eval-pcard-score num-tabular" style={{ color }}>
          {card.score}
          <span className="eval-pcard-score-ring" style={{ background: `conic-gradient(${color} ${card.score}%, var(--muted) 0)` }} aria-hidden />
        </span>
        <ChevronDown
          size={15}
          className={`shrink-0 text-ink-subtle transition-transform duration-300 ${open ? "rotate-180" : ""}`}
        />
      </button>
      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.3, ease: [0.22, 1, 0.36, 1] }}
            className="overflow-hidden"
          >
            <div className="eval-pcard-body">
              {card.highlights.length > 0 && (
                <div className="eval-pcard-col">
                  <p className="eval-pcard-label text-[var(--success)]">
                    <BadgeCheck size={12} /> 亮点
                  </p>
                  <ul className="eval-pcard-list">
                    {card.highlights.map((h, i) => (
                      <li key={i}>
                        <EvalRichText text={t(h)} />
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              {card.risks.length > 0 && (
                <div className="eval-pcard-col">
                  <p className="eval-pcard-label text-[var(--warning-ink)]">
                    <CircleAlert size={12} /> 风险
                  </p>
                  <ul className="eval-pcard-list">
                    {card.risks.map((r, i) => (
                      <li key={i}>
                        <EvalRichText text={t(r)} />
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              {card.deep_questions.length > 0 && (
                <div className="eval-pcard-questions">
                  <p className="eval-pcard-label text-[var(--primary-ink)]">
                    <CircleHelp size={12} /> 面试官必问
                  </p>
                  <div className="eval-pcard-qwrap">
                    {card.deep_questions.map((q, i) => (
                      <p key={i} className="eval-pcard-q">
                        <EvalRichText text={t(q)} />
                      </p>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

export function ProjectCards({ cards }: { cards: ProjectCardData[] }) {
  const cleaned = cards.filter((c) => c.name);
  if (cleaned.length === 0) return null;
  return (
    <section className="eval-section">
      <span className="eval-label">项目深挖卡片</span>
      <div className="eval-pcard-stack">
        {cleaned.map((c, i) => (
          <ProjectCardItem key={`${c.name}-${i}`} card={c} index={i} />
        ))}
      </div>
    </section>
  );
}

"use client";

import { useState } from "react";
import { AnimatePresence, motion, useInView, useReducedMotion } from "framer-motion";
import { useRef } from "react";
import {
  BadgeCheck,
  Building2,
  ChevronDown,
  CircleHelp,
  CircleAlert,
  GitBranch,
  MapPin,
  ShieldCheck,
  ShieldQuestion,
  Sparkles,
} from "lucide-react";
import type {
  CareerAnalysisData,
  CompanyFitData,
  ProjectCardData,
  SectionReview,
  SkillTrustData,
} from "@/types";
import { normalizeCnPunctuation } from "@/lib/cnText";
import { EvalRichText } from "./EvalRichText";

const t = normalizeCnPunctuation;

function scoreColor(score: number): string {
  if (score >= 80) return "var(--success)";
  if (score >= 60) return "var(--primary)";
  if (score >= 40) return "var(--warning)";
  return "var(--danger)";
}

/* ── 分区审阅热力条 ─────────────────────────────── */

/** 简历分区审阅:分段热力条 + hover 浮出判词,点击选中看详情。 */
export function SectionHeatmap({ reviews }: { reviews: SectionReview[] }) {
  const cleaned = reviews.filter((r) => r.section && r.score > 0);
  const [active, setActive] = useState(0);
  if (cleaned.length === 0) return null;
  const current = cleaned[Math.min(active, cleaned.length - 1)]!;

  return (
    <section className="eval-section">
      <span className="eval-label">分区审阅热力</span>
      <div className="eval-heat" role="tablist" aria-label="简历分区审阅">
        {cleaned.map((r, i) => (
          <button
            key={`${r.section}-${i}`}
            type="button"
            role="tab"
            aria-selected={i === active}
            onClick={() => setActive(i)}
            className={`eval-heat-seg ${i === active ? "is-active" : ""}`}
            style={{
              flexGrow: Math.max(r.detail.length, 40),
              "--seg-color": scoreColor(r.score),
            } as React.CSSProperties}
          >
            <span className="eval-heat-score num-tabular">{r.score}</span>
            <span className="eval-heat-name">{r.section}</span>
          </button>
        ))}
      </div>
      <AnimatePresence mode="wait">
        <motion.div
          key={current.section}
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -6 }}
          transition={{ duration: 0.22 }}
          className="eval-heat-detail"
        >
          <p className="eval-heat-verdict">
            <MapPin size={13} className="shrink-0 text-[var(--primary)]" />
            {t(current.verdict)}
          </p>
          <p className="eval-heat-body">
            <EvalRichText text={t(current.detail)} />
          </p>
        </motion.div>
      </AnimatePresence>
    </section>
  );
}

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

/* ── 技能核验三分板 ─────────────────────────────── */

const TRUST_COLS: Array<{
  key: keyof SkillTrustData;
  title: string;
  hint: string;
  icon: React.ReactNode;
  cls: string;
}> = [
  {
    key: "solid",
    title: "实证技能",
    hint: "有项目与数字背书,面试可放心主讲",
    icon: <ShieldCheck size={13} />,
    cls: "is-solid",
  },
  {
    key: "claimed",
    title: "仅罗列",
    hint: "只在技能清单出现,被追问容易露怯",
    icon: <ShieldQuestion size={13} />,
    cls: "is-claimed",
  },
  {
    key: "missing",
    title: "岗位缺失",
    hint: "目标岗高频要求,简历完全没提",
    icon: <Sparkles size={13} />,
    cls: "is-missing",
  },
];

export function SkillTrustBoard({ trust }: { trust: SkillTrustData }) {
  const filled = TRUST_COLS.filter((c) => (trust[c.key]?.length ?? 0) > 0);
  if (filled.length === 0) return null;

  return (
    <section className="eval-section">
      <span className="eval-label">技能核验三分板</span>
      <div className="eval-trust-grid">
        {filled.map((col) => {
          const items = trust[col.key] ?? [];
          return (
            <div key={col.key} className={`eval-trust-col ${col.cls}`}>
              <p className="eval-trust-title">
                {col.icon}
                {col.title}
                <span className="eval-trust-count num-tabular">{items.length}</span>
              </p>
              <p className="eval-trust-hint">{col.hint}</p>
              <div className="eval-trust-chips">
                {items.map((s, i) => (
                  <span key={i} className="eval-trust-chip">
                    {s}
                  </span>
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}

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

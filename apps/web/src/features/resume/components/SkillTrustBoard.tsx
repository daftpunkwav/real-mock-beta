"use client";

import { ShieldCheck, ShieldQuestion, Sparkles } from "lucide-react";
import type { SkillTrustData } from "@/types";

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

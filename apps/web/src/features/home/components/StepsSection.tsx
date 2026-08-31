"use client";

import Link from "next/link";
import { motion, useReducedMotion } from "framer-motion";
import { ArrowRight } from "lucide-react";
import { STEPS } from "../content";
import { ease } from "../motion";

export function StepsSection() {
  const reduce = useReducedMotion();

  return (
    <section className="bg-surface-alt border-b border-surface-border">
      <div className="mx-auto max-w-[1320px] px-5 sm:px-6 lg:px-8 py-14 sm:py-20">
        <div className="page-header">
          <div>
            <p className="page-eyebrow">Onboarding</p>
            <h2 className="page-title">三步开始</h2>
          </div>
          <p className="page-desc">密钥 → 简历 → 面试,本地即可跑通。</p>
        </div>

        <div className="grid grid-cols-1 gap-3 md:grid-cols-3 md:gap-4">
          {STEPS.map((step, i) => (
            <motion.div
              key={step.n}
              initial={reduce ? false : { opacity: 0, y: 8 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: "-40px" }}
              transition={{ duration: 0.32, delay: i * 0.06, ease }}
            >
              <Link
                href={step.href}
                className="group surface-card-hover relative flex h-full flex-col p-5 sm:p-6"
              >
                <div className="mb-5 flex items-start justify-between">
                  <span className="font-mono text-xs font-semibold tracking-wide text-brand">
                    {step.n}
                  </span>
                  <span className="icon-badge icon-badge-muted group-hover:icon-badge-brand transition-colors">
                    <step.icon size={15} strokeWidth={1.75} />
                  </span>
                </div>
                <h3 className="mb-1.5 text-[15px] font-semibold text-ink">{step.title}</h3>
                <p className="flex-1 text-[13px] leading-relaxed text-ink-muted">{step.desc}</p>
                <div className="mt-5 flex items-center gap-1 text-[12px] font-medium text-brand">
                  <span>前往</span>
                  <ArrowRight
                    size={12}
                    className="btn-arrow transition-transform"
                  />
                </div>
                {i < STEPS.length - 1 && (
                  <span
                    className="pointer-events-none absolute right-[-10px] top-1/2 hidden h-5 w-5 -translate-y-1/2 items-center justify-center rounded-full border border-surface-border bg-surface-card text-ink-subtle md:flex"
                    aria-hidden
                  >
                    <ArrowRight size={10} />
                  </span>
                )}
              </Link>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
}

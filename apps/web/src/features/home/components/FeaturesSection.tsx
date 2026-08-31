"use client";

import { motion, useReducedMotion } from "framer-motion";
import { ArrowUpRight } from "lucide-react";
import { FEATURES } from "../content";
import { ease } from "../motion";
import { TintIcon } from "./TintIcon";

export function FeaturesSection() {
  const reduce = useReducedMotion();

  return (
    <section className="bg-surface border-b border-surface-border">
      <div className="mx-auto max-w-[1320px] px-5 sm:px-6 lg:px-10 py-14 sm:py-20">
        <div className="page-header">
          <div>
            <p className="page-eyebrow">Capabilities</p>
            <h2 className="page-title">为真实面试准备的工具链</h2>
            <p className="page-desc mt-2">
              从准备到报告,Agent 全链路协助,而不是刷固定题库。
            </p>
          </div>
        </div>

        <div className="mt-8 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 lg:gap-4">
          {FEATURES.map((f, i) => (
            <motion.div
              key={f.title}
              initial={reduce ? false : { opacity: 0, y: 6 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: "-40px" }}
              transition={{ duration: 0.3, delay: i * 0.04, ease }}
            >
              <div className="group surface-card-hover h-full p-5">
                <div className="mb-4 flex items-center justify-between">
                  <TintIcon icon={f.icon} tint={f.tint} />
                  <ArrowUpRight
                    size={14}
                    className="text-ink-subtle opacity-0 transition-all group-hover:translate-x-0.5 group-hover:-translate-y-0.5 group-hover:opacity-100 group-hover:text-brand"
                  />
                </div>
                <h3 className="mb-1 text-[14px] font-semibold text-ink">{f.title}</h3>
                <p className="text-[13px] leading-relaxed text-ink-muted">{f.desc}</p>
              </div>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
}

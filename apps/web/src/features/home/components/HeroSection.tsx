"use client";

import Link from "next/link";
import { motion, useReducedMotion } from "framer-motion";
import { ArrowRight, ArrowUpRight } from "lucide-react";
import { STATS } from "../content";
import { ease } from "../motion";
import { InterviewPreview } from "./InterviewPreview";

export function HeroSection() {
  const reduce = useReducedMotion();

  return (
    <section className="relative overflow-hidden border-b border-surface-border">
      <div className="absolute inset-0 gradient-google opacity-90" aria-hidden />
      <div className="absolute inset-0 grid-google opacity-40 [mask-image:radial-gradient(ellipse_at_center,black,transparent_70%)]" aria-hidden />

      <div className="relative mx-auto max-w-[1320px] px-5 sm:px-6 lg:px-8 pt-14 pb-16 sm:pt-16 sm:pb-20 lg:pt-20">
        <div className="grid grid-cols-1 items-center gap-10 lg:grid-cols-12 lg:gap-8">
          {/* 左 */}
          <div className="lg:col-span-6 xl:col-span-5">
            <motion.div
              initial={reduce ? false : { opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.32, ease }}
              className="inline-flex items-center gap-2 rounded-full border border-surface-border bg-surface-card px-3 py-1 shadow-xs"
            >
              <span className="relative flex h-1.5 w-1.5">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-[var(--success)] opacity-50" />
                <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-[var(--success)]" />
              </span>
              <span className="text-[11px] font-medium text-ink-muted">
                开源 · BYOK · 数据本地
              </span>
            </motion.div>

            <motion.h1
              initial={reduce ? false : { opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.4, delay: 0.04, ease }}
              className="mt-5 text-[clamp(2rem,4.5vw,3.25rem)] font-semibold leading-[1.05] tracking-[-0.03em] text-ink text-balance"
            >
              用真实流程
              <br />
              <span className="text-brand-grad">练好下一场面试</span>
            </motion.h1>

            <motion.p
              initial={reduce ? false : { opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.36, delay: 0.1, ease }}
              className="mt-5 max-w-[40ch] text-[14px] sm:text-[15px] leading-[1.65] text-ink-muted"
            >
              上传简历,选择目标公司,体验追问与音视频交互。自带 API Key,无需注册账号。
            </motion.p>

            <motion.div
              initial={reduce ? false : { opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.32, delay: 0.16, ease }}
              className="mt-7 flex flex-wrap items-center gap-2.5"
            >
              <Link href="/interview" className="btn-primary">
                开始面试
                <ArrowRight size={14} className="btn-arrow transition-transform" />
              </Link>
              <Link href="/resume" className="btn-secondary">
                上传简历
              </Link>
              <Link
                href="/prep"
                className="btn-tertiary text-[var(--primary)]"
              >
                先看看 <ArrowUpRight size={13} />
              </Link>
            </motion.div>

            {/* 指标 */}
            <motion.div
              initial={reduce ? false : { opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: 0.24, duration: 0.4 }}
              className="mt-10 grid grid-cols-2 gap-3 sm:grid-cols-4"
            >
              {STATS.map((s) => (
                <div
                  key={s.label}
                  className="surface-card-hover px-4 py-3"
                >
                  <p className="font-mono text-2xl font-semibold tracking-tight text-ink num-tabular">
                    {s.value.toLocaleString()}
                    <span className="text-brand">{s.suffix}</span>
                  </p>
                  <p className="mt-1 text-[11px] text-ink-subtle">{s.label}</p>
                </div>
              ))}
            </motion.div>
          </div>

          {/* 右 */}
          <motion.div
            initial={reduce ? false : { opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.45, delay: 0.12, ease }}
            className="lg:col-span-6 xl:col-span-7 lg:pl-4"
          >
            <InterviewPreview />
          </motion.div>
        </div>
      </div>
    </section>
  );
}

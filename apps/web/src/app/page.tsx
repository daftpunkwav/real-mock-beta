"use client";

import Link from "next/link";
import { motion, useReducedMotion } from "framer-motion";
import {
  Mic,
  FileText,
  ArrowRight,
  ArrowUpRight,
  Sparkles,
  MessageSquare,
  Building2,
  BarChart3,
  Video,
  BookOpen,
  Shield,
  KeyRound,
  TrendingUp,
} from "lucide-react";

const STEPS = [
  {
    n: "01",
    title: "接入密钥",
    desc: "BYOK 配置 LLM,本地加密存储",
    href: "/settings",
    icon: KeyRound,
  },
  {
    n: "02",
    title: "上传简历",
    desc: "解析档案,生成多维度评价",
    href: "/resume",
    icon: FileText,
  },
  {
    n: "03",
    title: "开始面试",
    desc: "选公司 + 岗位,进入模拟",
    href: "/interview",
    icon: Mic,
  },
];

const FEATURES = [
  { icon: Sparkles, title: "动态出题", desc: "基于简历与岗位实时生成问题,不刷固定题库。", tint: "brand" },
  { icon: MessageSquare, title: "深度追问", desc: "回答含糊时自动深挖细节,贴近真实面试官节奏。", tint: "green" },
  { icon: Building2, title: "企业风格", desc: "字节 / 腾讯 / 阿里等公司面试风格可切换。", tint: "warning" },
  { icon: Video, title: "音视频交互", desc: "摄像头与语音实时参与,还原临场压力。", tint: "danger" },
  { icon: BookOpen, title: "面试准备", desc: "教练式辅导与面经检索,上场前系统梳理。", tint: "brand" },
  { icon: BarChart3, title: "报告与成长", desc: "场次评分、改进建议,弱项跨场次沉淀。", tint: "green" },
] as const;

const STATS = [
  { value: 50, suffix: "+", label: "企业风格库" },
  { value: 1000, suffix: "+", label: "题目规模" },
  { value: 100, suffix: "%", label: "本地可用" },
  { value: 0, suffix: "", label: "账号注册" },
];

const ease = [0.2, 0, 0, 1] as const;

function InterviewPreview() {
  return (
    <div className="relative">
      <div
        className="absolute -inset-4 rounded-xl opacity-60 blur-2xl"
        style={{
          background:
            "radial-gradient(ellipse at 50% 80%, color-mix(in srgb, var(--primary) 18%, transparent), transparent 70%)",
        }}
      />
      <div className="surface-card relative overflow-hidden">
        {/* 顶栏 */}
        <div className="flex items-center justify-between border-b border-surface-border bg-surface-alt px-4 py-2.5">
          <div className="flex items-center gap-2">
            <span className="relative flex h-2 w-2">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-[var(--success)] opacity-40" />
              <span className="relative inline-flex h-2 w-2 rounded-full bg-[var(--success)]" />
            </span>
            <span className="text-xs font-medium text-ink">模拟面试进行中</span>
            <span className="chip chip-green !text-[10px]">Live</span>
          </div>
          <span className="font-mono text-[11px] tracking-wider text-ink-subtle">12:34</span>
        </div>

        {/* 对话 */}
        <div className="space-y-3 p-4 sm:p-5">
          {/* 面试官 */}
          <div className="flex gap-3">
            <div className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-[var(--info-soft)] text-[11px] font-semibold text-[var(--info-ink)]">
              面
            </div>
            <div className="min-w-0 flex-1">
              <div className="mb-1 flex items-center gap-2">
                <span className="text-[11px] font-medium text-ink">面试官</span>
                <span className="chip chip-blue !text-[10px]">字节跳动 · 后端</span>
              </div>
              <div className="rounded-md rounded-tl-sm border border-surface-border bg-surface-alt px-3 py-2.5">
                <p className="text-[13px] leading-relaxed text-ink-muted">
                  请介绍一下你最近负责的项目,重点说明你做了什么决策,以及结果如何衡量。
                </p>
              </div>
            </div>
          </div>

          {/* 候选人 */}
          <div className="flex flex-row-reverse gap-3">
            <div className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-[var(--primary)] text-[11px] font-semibold text-white">
              我
            </div>
            <div className="min-w-0 flex-1">
              <p className="mb-1 text-right text-[11px] font-medium text-ink-subtle">你</p>
              <div className="rounded-md rounded-tr-sm border border-[color-mix(in_srgb,var(--primary)_22%,var(--border))] bg-[var(--info-soft)] px-3 py-2.5">
                <p className="text-[13px] leading-relaxed text-[var(--info-ink)]">
                  上个季度我负责订单履约链路改造,把峰值延迟从 320ms 降到 110ms,QPS 提升 2.4 倍…
                </p>
                <span className="mt-1.5 inline-block h-3 w-[2px] animate-pulse bg-[var(--primary)] align-middle" />
              </div>
            </div>
          </div>
        </div>

        {/* 底栏 */}
        <div className="flex items-center gap-4 border-t border-surface-border bg-surface-alt px-4 py-2">
          <div className="flex items-center gap-1.5 text-[11px] text-ink-muted">
            <Video size={11} className="text-[var(--primary)]" />
            视频已连接
          </div>
          <div className="flex items-center gap-1.5 text-[11px] text-ink-muted">
            <Mic size={11} className="text-[var(--success)]" />
            语音识别中
          </div>
          <div className="ml-auto flex items-center gap-1.5 text-[11px] font-medium text-[var(--success)]">
            <TrendingUp size={11} />
            综合表现 82
          </div>
        </div>
      </div>
    </div>
  );
}

function TintIcon({ icon: Icon, tint }: { icon: typeof Sparkles; tint: string }) {
  const cls = {
    brand: "icon-badge icon-badge-brand",
    green: "icon-badge icon-badge-success",
    warning: "icon-badge icon-badge-warning",
    danger: "icon-badge icon-badge-danger",
  }[tint] ?? "icon-badge";
  return (
    <span className={cls}>
      <Icon size={16} strokeWidth={1.75} />
    </span>
  );
}

export default function HomePage() {
  const reduce = useReducedMotion();

  return (
    <div className="min-h-full anim-rise">
      {/* —— Hero —— */}
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

      {/* —— 三步 —— */}
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

      {/* —— 能力 —— */}
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

      {/* —— 信任点 —— */}
      <section className="border-b border-surface-border bg-surface-alt">
        <div className="mx-auto max-w-[1320px] px-5 sm:px-6 lg:px-10 py-10 sm:py-14">
          <div className="grid grid-cols-1 gap-5 sm:grid-cols-3 sm:gap-0">
            {[
              { icon: Shield, tint: "icon-badge-success", title: "本地优先", desc: "面试数据与密钥默认留在本机,不强制上云" },
              { icon: KeyRound, tint: "icon-badge-brand", title: "自带密钥", desc: "BYOK 接入你的 LLM,成本与模型自己掌控" },
              { icon: Sparkles, tint: "icon-badge-warning", title: "开源可审计", desc: "代码透明,流程可改,适合二次定制" },
            ].map((it, i) => (
              <div
                key={it.title}
                className={`flex items-start gap-3 sm:px-6 ${i > 0 ? "sm:border-l sm:border-surface-border" : ""}`}
              >
                <span className={`icon-badge ${it.tint}`}>
                  <it.icon size={15} strokeWidth={2} />
                </span>
                <div>
                  <p className="text-[14px] font-semibold text-ink">{it.title}</p>
                  <p className="mt-1 text-[13px] leading-relaxed text-ink-muted">{it.desc}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* —— CTA —— */}
      <section className="bg-surface">
        <div className="mx-auto max-w-[1320px] px-5 sm:px-6 lg:px-10 py-14 sm:py-16">
          <div className="relative overflow-hidden rounded-lg border border-surface-border bg-surface-card p-7 sm:p-10">
            <div
              className="pointer-events-none absolute inset-0 opacity-90"
              style={{
                background:
                  "radial-gradient(640px 260px at 90% 0%, color-mix(in srgb, var(--primary) 16%, transparent), transparent 55%), radial-gradient(420px 200px at 8% 100%, color-mix(in srgb, var(--chart-5) 14%, transparent), transparent 50%)",
              }}
              aria-hidden
            />
            <div className="relative flex flex-col items-start justify-between gap-6 sm:flex-row sm:items-center">
              <div>
                <p className="page-eyebrow">Ready to start</p>
                <h2 className="mt-2 text-[20px] sm:text-[24px] font-semibold leading-tight tracking-tight text-ink">
                  下一场面试,现在开始练
                </h2>
                <p className="mt-2 text-[13px] text-ink-muted">
                  本地优先 · BYOK · 无需注册账号
                </p>
              </div>
              <Link
                  href="/interview"
                  className="btn-primary"
                >
                  开始模拟面试
                  <ArrowRight size={14} className="btn-arrow transition-transform" />
                </Link>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}

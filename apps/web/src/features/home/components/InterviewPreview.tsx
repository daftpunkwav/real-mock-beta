"use client";

import { Mic, TrendingUp, Video } from "lucide-react";

export function InterviewPreview() {
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

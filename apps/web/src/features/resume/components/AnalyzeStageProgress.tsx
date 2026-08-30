"use client";

import { useEffect, useState } from "react";
import { Check } from "lucide-react";

const STAGES = [
  "正在通读简历全文…",
  "审阅排版、字体与信息层级…",
  "规划检索词,联网核对岗位要求…",
  "交叉验证项目事实与数据…",
  "汇总十维评分与最终结论…",
];

/** 深度评价等待态:阶段轮播 + 步骤点,缓解 1-3 分钟长等待的焦虑。 */
export function AnalyzeStageProgress() {
  const [stage, setStage] = useState(0);

  useEffect(() => {
    const timer = setInterval(
      () => setStage((s) => Math.min(s + 1, STAGES.length - 1)),
      8000,
    );
    return () => clearInterval(timer);
  }, []);

  return (
    <div className="py-12 text-center">
      <div className="relative mx-auto mb-6 h-16 w-16">
        <span className="absolute inset-0 rounded-full border-2 border-[var(--primary)]/25" />
        <span className="absolute inset-0 rounded-full border-2 border-transparent border-t-[var(--primary)] anim-spin" />
        <span className="absolute inset-3 rounded-full bg-[var(--info-soft)]" />
        <span className="absolute inset-0 flex items-center justify-center text-[var(--primary)]">
          <span className="h-2 w-2 animate-pulse rounded-full bg-current" />
        </span>
      </div>
      <p className="mb-1.5 text-[13px] font-medium tracking-[0.04em] text-ink">
        正在生成深度评价
      </p>

      <div className="mx-auto mt-5 flex max-w-xs flex-col gap-2 text-left">
        {STAGES.map((s, i) => {
          const done = i < stage;
          const active = i === stage;
          return (
            <div
              key={s}
              className={`flex items-center gap-2.5 text-[12px] transition-all duration-500 ${
                active
                  ? "text-ink"
                  : done
                    ? "text-ink-subtle"
                    : "text-ink-subtle/50"
              }`}
            >
              <span
                className={`flex h-4 w-4 shrink-0 items-center justify-center rounded-full border ${
                  done
                    ? "border-[var(--success)] bg-[var(--success)] text-white"
                    : active
                      ? "border-[var(--primary)]"
                      : "border-surface-border"
                }`}
              >
                {done ? (
                  <Check size={10} strokeWidth={3} />
                ) : active ? (
                  <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-[var(--primary)]" />
                ) : null}
              </span>
              <span className={active ? "font-medium" : ""}>{s}</span>
            </div>
          );
        })}
      </div>
      <p className="mx-auto mt-5 max-w-sm text-[11px] leading-relaxed tracking-[0.03em] text-ink-subtle">
        含联网检索与十维审阅,通常需要 1–3 分钟
      </p>
    </div>
  );
}

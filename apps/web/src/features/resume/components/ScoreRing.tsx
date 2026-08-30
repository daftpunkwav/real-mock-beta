"use client";

import { useEffect, useRef, useState } from "react";
import { useInView, useReducedMotion } from "framer-motion";

function scoreColor(score: number): { ring: string; ink: string } {
  if (score >= 80) return { ring: "var(--success)", ink: "var(--success)" };
  if (score >= 60) return { ring: "var(--primary)", ink: "var(--primary)" };
  if (score >= 40) return { ring: "var(--warning)", ink: "var(--warning)" };
  return { ring: "var(--danger)", ink: "var(--danger)" };
}

/** 综合分圆环:入视后从 0 扫到目标分,颜色按档位变化。 */
export function ScoreRing({ score, size = 112 }: { score: number; size?: number }) {
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
    // 下一帧再触发,保证初始 dashoffset 先完成挂载
    const raf = requestAnimationFrame(() => setShown(true));
    return () => cancelAnimationFrame(raf);
  }, [inView, reduce]);

  const clamped = Math.max(0, Math.min(100, Math.round(score)));
  const radius = size / 2 - 9;
  const circumference = 2 * Math.PI * radius;
  const progress = shown ? clamped / 100 : 0;
  const { ring } = scoreColor(clamped);

  return (
    <div
      ref={ref}
      className="relative shrink-0"
      style={{ width: size, height: size }}
      role="img"
      aria-label={`综合得分 ${clamped} 分`}
    >
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="var(--muted)"
          strokeWidth={8}
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={ring}
          strokeWidth={8}
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={circumference * (1 - progress)}
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
          style={{
            transition: "stroke-dashoffset 1.3s cubic-bezier(0.22, 1, 0.36, 1), stroke 0.6s",
          }}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span
          className="num-tabular font-semibold leading-none tracking-tight"
          style={{ fontSize: size * 0.3, color: ring }}
        >
          {clamped}
        </span>
        <span className="mt-1 text-[10px] font-medium tracking-[0.22em] text-ink-subtle">
          综合
        </span>
      </div>
    </div>
  );
}

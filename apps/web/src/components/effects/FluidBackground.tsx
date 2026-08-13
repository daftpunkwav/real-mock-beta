"use client";

import { useEffect, useRef } from "react";

/**
 * 极轻柔光：单色蓝系慢漂移，作 hero 氛围层。
 * 低对比、慢速、尊重 reduced-motion。
 */
export function FluidBackground({ className = "" }: { className?: string }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const rafRef = useRef(0);

  useEffect(() => {
    const el = canvasRef.current;
    if (!el) return;
    const ctx2d = el.getContext("2d", { alpha: true });
    if (!ctx2d) return;
    const canvas = el;
    const ctx = ctx2d;

    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    let w = 0;
    let h = 0;
    let t = 0;
    let last = performance.now();

    // 两团主光 + 一抹辅光，避免多色斑点
    const spots = [
      { cx: 0.72, cy: 0.28, r: 0.52, rgb: "66,133,244", a: 0.09, f: 0.12, p: 0.2, ax: 0.04, ay: 0.03 },
      { cx: 0.28, cy: 0.62, r: 0.4, rgb: "138,180,248", a: 0.07, f: 0.1, p: 1.6, ax: 0.035, ay: 0.04 },
      { cx: 0.55, cy: 0.85, r: 0.32, rgb: "26,115,232", a: 0.04, f: 0.08, p: 2.4, ax: 0.025, ay: 0.02 },
    ];

    function resize() {
      const dpr = Math.min(window.devicePixelRatio || 1, 1.5);
      const rect = canvas.getBoundingClientRect();
      w = Math.max(1, rect.width);
      h = Math.max(1, rect.height);
      canvas.width = Math.floor(w * dpr);
      canvas.height = Math.floor(h * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    }

    function frame(now: number) {
      const dt = Math.min(0.05, (now - last) / 1000);
      last = now;
      if (!reduce) t += dt * 0.4;

      ctx.clearRect(0, 0, w, h);

      for (const s of spots) {
        const ph = Math.sin(t * s.f + s.p);
        const ph2 = Math.sin(t * s.f * 1.35 + s.p * 0.7);
        const x = (s.cx + ph * s.ax + ph2 * s.ax * 0.3) * w;
        const y = (s.cy + Math.cos(t * s.f * 0.85 + s.p) * s.ay + ph2 * s.ay * 0.2) * h;
        const r = Math.min(w, h) * s.r * (0.96 + 0.04 * Math.sin(t * 0.25 + s.p));

        const g = ctx.createRadialGradient(x, y, 0, x, y, r);
        g.addColorStop(0, `rgba(${s.rgb},${s.a})`);
        g.addColorStop(0.55, `rgba(${s.rgb},${s.a * 0.28})`);
        g.addColorStop(1, `rgba(${s.rgb},0)`);
        ctx.fillStyle = g;
        ctx.beginPath();
        ctx.arc(x, y, r, 0, Math.PI * 2);
        ctx.fill();
      }

      if (!reduce) rafRef.current = requestAnimationFrame(frame);
    }

    resize();
    last = performance.now();
    if (reduce) frame(last);
    else rafRef.current = requestAnimationFrame(frame);

    window.addEventListener("resize", resize);
    return () => {
      window.removeEventListener("resize", resize);
      cancelAnimationFrame(rafRef.current);
    };
  }, []);

  return (
    <canvas
      ref={canvasRef}
      className={`absolute inset-0 w-full h-full pointer-events-none ${className}`}
      aria-hidden
    />
  );
}

"use client";

import { useEffect, useRef } from "react";

interface Particle {
  x: number;
  y: number;
  vx: number;
  vy: number;
  r: number;
  o: number;
  phase: number;
}

/**
 * 极淡点场：稀疏、无连线、弱流场，仅作 hero 质感点缀。
 */
export function ParticleField({
  className = "",
  density = 0.35,
}: {
  className?: string;
  density?: number;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const partsRef = useRef<Particle[]>([]);
  const rafRef = useRef(0);
  const tRef = useRef(0);

  useEffect(() => {
    const el = canvasRef.current;
    if (!el) return;
    const ctx2d = el.getContext("2d", { alpha: true });
    if (!ctx2d) return;
    const canvas = el;
    const ctx = ctx2d;

    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    let W = 0;
    let H = 0;
    let last = performance.now();

    function field(x: number, y: number, tt: number) {
      const nx = x / Math.max(W, 1);
      const ny = y / Math.max(H, 1);
      return (
        Math.sin(nx * 1.8 + tt * 0.35) * Math.cos(ny * 1.5 - tt * 0.25) * 0.6 +
        Math.sin(nx * 3.2 - ny * 1.8 + tt * 0.5) * 0.4
      );
    }

    function curl(x: number, y: number, tt: number) {
      const e = 14;
      const dFdx = (field(x + e, y, tt) - field(x - e, y, tt)) / (2 * e);
      const dFdy = (field(x, y + e, tt) - field(x, y - e, tt)) / (2 * e);
      return { u: dFdy * 40, v: -dFdx * 40 };
    }

    function resize() {
      const dpr = Math.min(window.devicePixelRatio || 1, 1.5);
      const rect = canvas.getBoundingClientRect();
      W = Math.max(1, rect.width);
      H = Math.max(1, rect.height);
      canvas.width = Math.floor(W * dpr);
      canvas.height = Math.floor(H * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

      const n = Math.min(36, Math.max(14, Math.floor((W * H) / 38000 * density)));
      const list: Particle[] = [];
      for (let i = 0; i < n; i++) {
        list.push({
          x: Math.random() * W,
          y: Math.random() * H,
          vx: 0,
          vy: 0,
          r: 0.8 + Math.random() * 1.1,
          o: 0.08 + Math.random() * 0.12,
          phase: Math.random() * Math.PI * 2,
        });
      }
      partsRef.current = list;
    }

    function step(now: number) {
      const dt = Math.min(0.033, (now - last) / 1000);
      last = now;
      if (!reduce) tRef.current += dt * 0.7;
      const t = tRef.current;
      const ps = partsRef.current;

      ctx.clearRect(0, 0, W, H);

      for (const p of ps) {
        const c = curl(p.x, p.y, t);
        p.vx += c.u * dt * 0.03;
        p.vy += c.v * dt * 0.03;

        const sp = Math.hypot(p.vx, p.vy);
        if (sp > 0.7) {
          p.vx = (p.vx / sp) * 0.7;
          p.vy = (p.vy / sp) * 0.7;
        }
        p.vx *= 0.99;
        p.vy *= 0.99;
        p.x += p.vx;
        p.y += p.vy;
        if (p.x < -6) p.x = W + 6;
        if (p.x > W + 6) p.x = -6;
        if (p.y < -6) p.y = H + 6;
        if (p.y > H + 6) p.y = -6;

        const pulse = 0.9 + 0.1 * Math.sin(t * 0.8 + p.phase);
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.r * pulse, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(66,133,244,${p.o * pulse})`;
        ctx.fill();
      }

      if (!reduce) rafRef.current = requestAnimationFrame(step);
    }

    resize();
    last = performance.now();
    if (reduce) step(last);
    else rafRef.current = requestAnimationFrame(step);

    window.addEventListener("resize", resize);
    return () => {
      window.removeEventListener("resize", resize);
      cancelAnimationFrame(rafRef.current);
    };
  }, [density]);

  return (
    <canvas
      ref={canvasRef}
      className={`absolute inset-0 w-full h-full pointer-events-none ${className}`}
      aria-hidden
    />
  );
}

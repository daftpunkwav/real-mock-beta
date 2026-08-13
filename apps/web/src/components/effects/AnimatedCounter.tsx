"use client";

import { useEffect, useRef, useState } from "react";
import { useInView, useReducedMotion } from "framer-motion";

interface AnimatedCounterProps {
  value: number;
  suffix?: string;
  prefix?: string;
  duration?: number;
  className?: string;
}

export function AnimatedCounter({
  value,
  suffix = "",
  prefix = "",
  duration = 1.4,
  className = "",
}: AnimatedCounterProps) {
  const [count, setCount] = useState(0);
  const ref = useRef<HTMLSpanElement>(null);
  const isInView = useInView(ref, { once: true, margin: "-40px" });
  const reduce = useReducedMotion();

  useEffect(() => {
    if (!isInView) return;
    if (reduce) {
      setCount(value);
      return;
    }

    let startTime: number | undefined;
    let animationFrame: number;

    function animate(timestamp: number) {
      if (startTime === undefined) startTime = timestamp;
      const progress = Math.min((timestamp - startTime) / (duration * 1000), 1);
      // easeOutCubic — 比 expo 更稳，数字不「冲」
      const eased = 1 - Math.pow(1 - progress, 3);
      setCount(Math.floor(eased * value));

      if (progress < 1) {
        animationFrame = requestAnimationFrame(animate);
      } else {
        setCount(value);
      }
    }

    animationFrame = requestAnimationFrame(animate);
    return () => cancelAnimationFrame(animationFrame);
  }, [isInView, value, duration, reduce]);

  return (
    <span ref={ref} className={className}>
      {prefix}
      {count}
      {suffix}
    </span>
  );
}

"use client";

import { useEffect, useRef, type RefObject } from "react";

/**
 * 任意包裹节点挂上这个 hook 后,会通过 IntersectionObserver
 * 在元素首次进入视口时给它加上 .is-in-view。
 *
 * - 进入视口前:`opacity:0; translateY(8px)`
 * - 进入视口后:还原成正常位置,配合 `var(--dur-slow) var(--ease)`
 *
 * 用法(必须把 hook 调用结果存到变量,然后传给 ref):
 * ```tsx
 * const revealRef = useReveal<HTMLDivElement>();
 * <div ref={revealRef}> ... </div>
 * ```
 */
export function useReveal<T extends HTMLElement = HTMLElement>(): RefObject<T | null> {
  const ref = useRef<T | null>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    // Reduced-motion: 直接展示
    if (
      typeof window !== "undefined" &&
      window.matchMedia?.("(prefers-reduced-motion: reduce)").matches
    ) {
      el.classList.add("is-in-view");
      return;
    }
    if (typeof IntersectionObserver === "undefined") {
      el.classList.add("is-in-view");
      return;
    }

    const reveal = () => el.classList.add("is-in-view");

    // 元素挂载时即检查:已在视口或父级隐藏(如 framer-motion 包裹)→ 直接展示。
    const rect = el.getBoundingClientRect();
    const inViewport =
      rect.width > 0 &&
      rect.height > 0 &&
      rect.bottom > 0 &&
      rect.right > 0 &&
      rect.top < (window.innerHeight || 0) &&
      rect.left < (window.innerWidth || 0);
    if (inViewport) {
      reveal();
      return;
    }

    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            reveal();
            observer.unobserve(entry.target);
          }
        }
      },
      { rootMargin: "0px 0px -5% 0px", threshold: 0.01 },
    );
    observer.observe(el);

    // 兜底:1.2s 内若仍未触发,主动展示(防止父级 transform / display 拦截 observer)
    const fallback = window.setTimeout(() => {
      reveal();
      observer.disconnect();
    }, 1200);

    return () => {
      observer.disconnect();
      window.clearTimeout(fallback);
    };
  }, []);

  return ref;
}

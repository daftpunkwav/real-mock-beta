"use client";

import { useEffect, useMemo, useState } from "react";
import { MarkdownContent } from "./MarkdownContent";

interface StreamingRevealProps {
  content: string;
  streaming: boolean;
  /** 相对 LLM 真实进度落后的字符数 */
  lag?: number;
  /** 每次追赶的字符数 */
  charsPerTick?: number;
  /** 追赶间隔（毫秒） */
  tickMs?: number;
}

/**
 * 流式输出：显示进度略落后于真实内容，全程 Markdown 渲染保持格式；
 * 流式结束后展示完整内容。
 */
export function StreamingReveal({
  content,
  streaming,
  lag = 2,
  charsPerTick = 1,
  tickMs = 16,
}: StreamingRevealProps) {
  const [visibleLength, setVisibleLength] = useState(0);

  useEffect(() => {
    if (!streaming) {
      setVisibleLength(content.length);
      return;
    }

    let raf = 0;
    let lastTick = 0;

    const step = (now: number) => {
      if (now - lastTick >= tickMs) {
        lastTick = now;
        setVisibleLength((prev) => {
          const target = Math.max(0, content.length - lag);
          if (prev >= target) return prev;
          return Math.min(prev + charsPerTick, target);
        });
      }
      raf = requestAnimationFrame(step);
    };

    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [content.length, streaming, lag, charsPerTick, tickMs]);

  useEffect(() => {
    if (content.length < visibleLength) {
      setVisibleLength(content.length);
    }
  }, [content.length, visibleLength]);

  const visibleContent = useMemo(
    () => (streaming ? content.slice(0, visibleLength) : content),
    [content, streaming, visibleLength],
  );

  if (!visibleContent && streaming) return null;

  return (
    <div className="relative">
      <MarkdownContent content={visibleContent} className={streaming ? "markdown-streaming" : ""} />
      {streaming && (
        <span className="ml-0.5 inline-block h-4 w-1.5 animate-pulse rounded-sm bg-[var(--primary)] align-middle" />
      )}
    </div>
  );
}

"use client";

import { MarkdownContent } from "./MarkdownContent";

interface StreamingRevealProps {
  content: string;
  streaming: boolean;
}

/**
 * 流式输出渲染:后端已是逐 token 真流式,这里直接跟随真实内容渲染,
 * 不再人为限速(旧的固定速率打字机追不上真实流速,流结束时会"瞬间补完")。
 * 全程保持 Markdown 渲染;流式中的不完整 Markdown 由渲染层自然降级。
 */
export function StreamingReveal({ content, streaming }: StreamingRevealProps) {
  return (
    <div className="relative">
      <MarkdownContent content={content} className={streaming ? "markdown-streaming" : ""} />
      {streaming && (
        <span className="ml-0.5 inline-block h-4 w-1.5 animate-pulse rounded-sm bg-[var(--primary)] align-middle" />
      )}
    </div>
  );
}

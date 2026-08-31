"use client";

import { memo, useMemo, useState } from "react";
import { ChevronRight, Brain } from "lucide-react";
import { StreamingReveal } from "@/components/StreamingReveal";
import { splitThinkAnswer, stripToolCallJson } from "@/lib/thinkStream";
import { cn } from "@/lib/utils";

interface ThinkAnswerMessageProps {
  /** 原始流式/完整内容(可含 think 标签) */
  content: string;
  /** 后端 reasoning 通道的思考内容(事件流/历史恢复),与内联 think 合并展示 */
  reasoning?: string;
  streaming?: boolean;
  className?: string;
}

/**
 * 准备页助手气泡:
 * - 思考过程默认折叠,可展开(内联 think 标签 + 后端 reasoning 事件合并)
 * - 正式回答走 StreamingReveal 流式渲染
 * - 剥离误流出的 tool JSON
 * memo 化:消息列表流式刷新时,content 未变的实例跳过重解析与重渲染
 */
export const ThinkAnswerMessage = memo(function ThinkAnswerMessage({
  content,
  reasoning,
  streaming = false,
  className,
}: ThinkAnswerMessageProps) {
  const [expanded, setExpanded] = useState(false);
  const reasoningText = (reasoning ?? "").trim();
  const { thinking, answer, inThinking, hasThinking } = useMemo(() => {
    const split = splitThinkAnswer(content);
    const merged = [reasoningText, split.thinking].filter(Boolean).join("\n\n");
    return {
      thinking: stripToolCallJson(merged),
      answer: stripToolCallJson(split.answer),
      inThinking: split.inThinking,
      hasThinking: split.hasThinking || !!reasoningText,
    };
  }, [content, reasoningText]);

  const showThinking = hasThinking || inThinking || thinking.length > 0;
  // 思考仍在推进:流式且尚无正式回答(工具轮思考事件或流内 think 未闭合)
  const thinkingActive = showThinking && streaming && !answer;
  // 仍在思考且尚无正式回答时,给用户可见反馈
  const thinkingOnly = showThinking && !answer && (streaming || inThinking);

  return (
    <div className={cn("min-w-0 space-y-2", className)}>
      {showThinking && (
        <div className="overflow-hidden rounded-md border border-surface-border bg-surface-alt">
          <button
            type="button"
            onClick={() => setExpanded((v) => !v)}
            className="flex w-full items-center gap-2 px-2.5 py-1.5 text-left text-[11px] text-ink-muted transition-colors hover:bg-surface-muted"
            aria-expanded={expanded}
          >
            <ChevronRight
              size={13}
              className={cn(
                "shrink-0 text-ink-subtle transition-transform",
                expanded && "rotate-90",
              )}
            />
            <Brain size={12} className="shrink-0 text-[var(--primary)]" />
            <span className="font-medium text-ink-muted">
              {thinkingActive ? "思考中…" : "思考过程"}
            </span>
            {!expanded && thinking && (
              <span className="line-clamp-1 min-w-0 flex-1 truncate text-ink-subtle">
                {thinking.slice(0, 48)}
                {thinking.length > 48 ? "…" : ""}
              </span>
            )}
            {thinkingActive && (
              <span className="ml-auto h-1.5 w-1.5 shrink-0 animate-pulse rounded-full bg-[var(--primary)]" />
            )}
          </button>
          {expanded && (
            <div className="border-t border-surface-border px-3 pb-2.5 pt-0">
              <pre className="mt-2 max-h-48 overflow-y-auto whitespace-pre-wrap font-mono text-[11px] leading-relaxed text-ink-subtle">
                {thinking || (streaming ? "…" : "（无内容）")}
                {thinkingActive && (
                  <span className="ml-0.5 inline-block h-3 w-1 animate-pulse bg-ink-subtle align-middle" />
                )}
              </pre>
            </div>
          )}
        </div>
      )}

      {thinkingOnly && !expanded && (
        <p className="flex items-center gap-1.5 text-[11px] text-ink-muted">
          <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-[var(--primary)]" />
          模型思考中,正式回答即将开始…
        </p>
      )}

      {answer ? (
        <StreamingReveal content={answer} streaming={streaming && !inThinking} />
      ) : streaming && !showThinking ? (
        <span className="flex items-center gap-2 text-[11px] text-ink-muted">
          <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-[var(--primary)]" />
          生成中…
        </span>
      ) : null}
    </div>
  );
});

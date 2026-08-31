import { memo } from "react";
import { Bot, User } from "lucide-react";
import type { PrepChatMessage } from "../types";
import { AgentSteps } from "./AgentSteps";
import { SearchResultCards } from "./SearchResultCards";
import { ThinkAnswerMessage } from "./ThinkAnswerMessage";

/**
 * 助手消息气泡(memo 化):流式 token 每帧刷新时,只有 content 变化的
 * 那条消息重渲染,历史消息整块跳过,避免长回复时全列表 Markdown 重解析。
 */
export const AssistantBubble = memo(function AssistantBubble({
  msg,
}: {
  msg: PrepChatMessage;
}) {
  return (
    <div className="flex gap-2.5">
      <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-[var(--info-soft)] text-[var(--info-ink)]">
        <Bot size={14} />
      </span>
      <div className="min-w-0 max-w-[88%] rounded-md rounded-bl-sm border border-surface-border bg-surface-alt px-3.5 py-2.5 text-[13px] leading-relaxed text-ink">
        <div className="space-y-2">
          {msg.streaming && msg.statusText ? (
            <p className="flex items-center gap-1.5 text-[11px] text-ink-muted">
              <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-[var(--primary)]" />
              {msg.statusText}
            </p>
          ) : null}
          {msg.steps && msg.steps.length > 0 ? <AgentSteps steps={msg.steps} /> : null}
          {msg.searchGroups && msg.searchGroups.length > 0 ? (
            <SearchResultCards groups={msg.searchGroups} />
          ) : null}
          <ThinkAnswerMessage
            content={msg.content}
            reasoning={msg.thinking}
            streaming={!!msg.streaming}
          />
        </div>
      </div>
    </div>
  );
});

/** 用户消息气泡（内联，无额外依赖） */
export function UserBubble({ content }: { content: string }) {
  return (
    <div className="flex flex-row-reverse gap-2.5">
      <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-[var(--primary)] text-white">
        <User size={14} />
      </span>
      <div className="min-w-0 max-w-[88%] rounded-md rounded-br-sm bg-[var(--primary)] px-3.5 py-2.5 text-[13px] leading-relaxed text-white">
        {content}
      </div>
    </div>
  );
}

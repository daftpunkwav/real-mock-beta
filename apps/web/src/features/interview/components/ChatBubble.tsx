"use client";

import { cn } from "@/lib/utils";

/** 面试聊天气泡：区分候选人/面试官/追问样式。 */
export function ChatBubble({
  role,
  content,
  streaming = false,
}: {
  role: string;
  content: string;
  streaming?: boolean;
}) {
  const isUser = role === "user";
  const isNudge = content.startsWith("[追问]");

  return (
    <div className={cn("flex gap-2", isUser ? "flex-row-reverse" : "flex-row")}>
      <span
        className={cn(
          "flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-[11px] font-bold text-white",
          isUser
            ? "bg-[var(--primary)]"
            : "bg-[var(--info)] text-[var(--info-ink)]",
        )}
      >
        {isUser ? "我" : "AI"}
      </span>
      <div className={cn("flex max-w-[85%] flex-col", isUser ? "items-end" : "items-start")}>
        <span className="mb-0.5 px-0.5 text-[10px] text-ink-subtle">
          {isUser ? "候选人" : isNudge ? "面试官 · 追问" : "面试官"}
          {streaming && " · 输入中"}
        </span>
        <div
          className={cn(
            "rounded-md px-3 py-2 text-[13px] leading-relaxed",
            isUser
              ? "rounded-tr-sm bg-[var(--primary)] text-white"
              : isNudge
                ? "rounded-tl-sm border border-[var(--warning)]/30 bg-[var(--warning-soft)] text-[var(--warning-ink)]"
                : "rounded-tl-sm border border-surface-border bg-surface-alt text-ink",
          )}
        >
          {content}
          {streaming && (
            <span className="ml-0.5 inline-block h-3.5 w-1.5 anim-pulse-dot rounded-sm bg-[var(--primary)] align-middle" />
          )}
        </div>
      </div>
    </div>
  );
}

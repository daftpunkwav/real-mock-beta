import type { ChatMessage } from "@/lib/api/contract";

/** 房间 UI 只展示候选人/面试官发言，过滤 system 与空内容。 */
export function toVisibleChatMessages(raw: ChatMessage[]): ChatMessage[] {
  return raw.filter(
    (m) => (m.role === "user" || m.role === "assistant") && Boolean(m.content?.trim()),
  );
}

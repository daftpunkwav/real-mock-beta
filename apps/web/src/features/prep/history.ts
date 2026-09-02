/** prep 历史消息 → 聊天消息 的归一化（形状校验，坏数据直接丢弃）。 */

import type { PrepHistoryMessage, PrepSearchGroup, PrepToolStep } from "@/lib/api/contract";
import type { PrepChatMessage } from "./types";

/** 历史消息里的执行步骤做形状校验,坏数据直接丢弃 */
export function normalizeSteps(raw: unknown): PrepToolStep[] | undefined {
  if (!Array.isArray(raw)) return undefined;
  const steps = raw
    .filter(
      (s): s is PrepToolStep =>
        !!s &&
        typeof s === "object" &&
        typeof (s as PrepToolStep).name === "string",
    )
    .map((s) => ({ name: s.name, query: String(s.query ?? "") }));
  return steps.length > 0 ? steps : undefined;
}

/** 历史消息里的检索卡片做形状校验,坏数据直接丢弃 */
export function normalizeSearchGroups(raw: unknown): PrepSearchGroup[] | undefined {
  if (!Array.isArray(raw)) return undefined;
  const groups = raw
    .filter(
      (g): g is PrepSearchGroup =>
        !!g &&
        typeof g === "object" &&
        typeof (g as PrepSearchGroup).query === "string" &&
        Array.isArray((g as PrepSearchGroup).results),
    )
    .map((g) => ({ query: g.query, results: g.results }));
  return groups.length > 0 ? groups : undefined;
}

/** 历史消息里的思考过程做形状校验,坏数据直接丢弃 */
export function normalizeThinking(raw: unknown): string | undefined {
  if (typeof raw !== "string") return undefined;
  const text = raw.trim();
  return text || undefined;
}

/** 后端历史消息 → 前端聊天消息(执行步骤/检索卡片/思考过程一并还原) */
export function mapHistoryMessages(
  list: PrepHistoryMessage[],
  nextId: (prefix: string) => string,
): PrepChatMessage[] {
  return (Array.isArray(list) ? list : [])
    .filter((m) => (m.role === "user" || m.role === "assistant") && m.content)
    .map((m) => ({
      id: nextId(m.role === "user" ? "u" : "a"),
      role: m.role === "user" ? "user" : "assistant",
      content: String(m.content),
      steps: normalizeSteps(m.steps),
      searchGroups: normalizeSearchGroups(m.search_groups),
      thinking: normalizeThinking(m.thinking),
    }));
}

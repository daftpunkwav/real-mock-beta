/** 面试准备域与 SSE 事件：Prep 聊天 / 历史 / 用量 / 报告流 / 通用错误事件。 */

import type { InterviewReport } from "./interview_core";

export interface SSEErrorEvent {
  type: "error";
  message: string;
  code?: string;
  retryable?: boolean;
}

export interface PrepSearchHit {
  title: string;
  url: string;
  snippet: string;
}

export interface PrepSearchGroup {
  query: string;
  results: PrepSearchHit[];
}

/** Agent 执行步骤(ReAct 行动记录,前端折叠展示) */
export interface PrepToolStep {
  name: string;
  query: string;
}

/** 历史消息接口返回的条目;assistant 消息可能附带执行步骤/检索卡片/思考过程 */
export interface PrepHistoryMessage {
  role: string;
  content: string;
  steps?: PrepToolStep[];
  search_groups?: PrepSearchGroup[];
  thinking?: string;
}

/** 辅导会话列表条目(对话记录按简历分组展示) */
export interface PrepSessionSummary {
  id: number;
  resume_id: number | null;
  resume_filename: string | null;
  summary: string;
  message_count: number;
  status: string;
  token_usage: number;
  /** 供应商回传的真实 token 累计(未回传为 0) */
  prompt_tokens?: number;
  completion_tokens?: number;
  cached_tokens?: number;
  created_at: string;
  updated_at: string;
}

/** 一轮(或累计)LLM token 用量;缓存命中 = cached_tokens / prompt_tokens */
export interface PrepUsageStats {
  prompt_tokens: number;
  completion_tokens: number;
  cached_tokens: number;
}

export type PrepSSEEvent =
  | { type: "token"; content: string }
  | { type: "status"; text: string }
  | { type: "thinking"; content: string }
  | { type: "tool_step"; name: string; query: string }
  | { type: "search_results"; groups: PrepSearchGroup[] }
  | { type: "ask_user"; question: string; options: string[] }
  | PrepUsageStats & { type: "usage" }
  | { type: "done"; token_usage: number }
  | SSEErrorEvent;

export type ReportSSEEvent =
  | { type: "token"; content: string }
  | { type: "done"; report: InterviewReport; token_usage: number }
  | SSEErrorEvent;

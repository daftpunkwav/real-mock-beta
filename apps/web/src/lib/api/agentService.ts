/** 智能体服务客户端（对应后端 ``agent_service``：面试准备教练） */

import type {
  PrepHistoryMessage,
  PrepMessageResponse,
  PrepSessionCreateResponse,
  PrepSessionSummary,
  PrepSSEEvent,
  PrepSearchGroup,
  PrepToolStep,
  PrepUsageStats,
  ResumePickerItem,
} from "@/types";
import { ApiError, consumeSSE, parseStructuredErrorResponse, request, resolveBackendUrl } from "@/lib/api/base";

export interface PrepStreamCallbacks {
  onToken: (token: string) => void;
  /** 模型思考过程(reasoning),每轮 LLM 调用一段,流式期间即时推送 */
  onThinking?: (text: string) => void;
  onSearchResults?: (groups: PrepSearchGroup[]) => void;
  /** 过程状态(如「正在分析问题…」),text 为空表示清除 */
  onStatus?: (text: string) => void;
  /** ReAct 工具步进(即时) */
  onToolStep?: (step: PrepToolStep) => void;
  /** Agent 请求用户弹窗选择 */
  onAskUser?: (question: string, options: string[]) => void;
  /** 本轮 LLM token 用量(供应商回传时可得) */
  onUsage?: (usage: PrepUsageStats) => void;
}

export const agentService = {
  listResumes: () => request<ResumePickerItem[]>("/v1/prep/resumes"),
  listPrepSessions: () => request<PrepSessionSummary[]>("/v1/prep/sessions"),
  createPrepSession: (data: {
    resume_id?: number;
    target_role?: string;
    target_company?: string;
  }) =>
    request<PrepSessionCreateResponse>("/v1/prep/sessions", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  prepMessages: (sessionId: number) =>
    request<PrepHistoryMessage[]>(
      `/v1/prep/sessions/${sessionId}/messages`,
    ),
  prepMessage: (sessionId: number, content: string) =>
    request<PrepMessageResponse>(`/v1/prep/sessions/${sessionId}/message`, {
      method: "POST",
      body: JSON.stringify({ content }),
    }),
  prepMessageStream: async (
    sessionId: number,
    content: string,
    callbacks: PrepStreamCallbacks,
    opts?: {
      modelProfileId?: number | null;
      reasoningEffort?: import("@/types").ReasoningEffort | null;
    },
  ): Promise<{ token_usage: number; usage: PrepUsageStats | null }> => {
    const { onToken, onThinking, onSearchResults, onStatus, onToolStep, onAskUser, onUsage } = callbacks;
    const url = resolveBackendUrl(
      `/api/v1/prep/sessions/${sessionId}/message/stream`,
    );
    let res: Response;
    try {
      res = await fetch(url, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          content,
          model_profile_id: opts?.modelProfileId ?? undefined,
          reasoning_effort: opts?.reasoningEffort ?? undefined,
        }),
      });
    } catch {
      throw new ApiError(
        `无法连接后端服务（流式 ${url}）。请确认 backend 已启动`,
        0,
      );
    }
    if (!res.ok) {
      const error = await parseStructuredErrorResponse(res);
      throw new ApiError(error.message, res.status, error);
    }

    let tokenUsage = 0;
    let usage: PrepUsageStats | null = null;
    await consumeSSE<PrepSSEEvent>(res, (event) => {
      if (event.type === "token" && typeof event.content === "string") {
        onToken(event.content);
      } else if (event.type === "thinking" && typeof event.content === "string") {
        onThinking?.(event.content);
      } else if (event.type === "status" && typeof event.text === "string") {
        onStatus?.(event.text);
      } else if (event.type === "tool_step" && typeof event.name === "string") {
        onToolStep?.({ name: event.name, query: String(event.query ?? "") });
      } else if (event.type === "search_results" && Array.isArray(event.groups)) {
        onSearchResults?.(event.groups);
      } else if (
        event.type === "ask_user" &&
        typeof event.question === "string" &&
        Array.isArray(event.options)
      ) {
        onAskUser?.(event.question, event.options.map(String));
      } else if (event.type === "usage") {
        usage = {
          prompt_tokens: Number(event.prompt_tokens) || 0,
          completion_tokens: Number(event.completion_tokens) || 0,
          cached_tokens: Number(event.cached_tokens) || 0,
        };
        onUsage?.(usage);
      } else if (event.type === "done") {
        tokenUsage = event.token_usage;
      } else if (event.type === "error") {
        throw new ApiError(event.message || "流式输出失败", res.status);
      }
    });
    return { token_usage: tokenUsage, usage };
  },
};

/** 智能体服务客户端（对应后端 ``agent_service``：面试准备教练） */

import type {
  PrepMessageResponse,
  PrepSessionCreateResponse,
  PrepSSEEvent,
  PrepSearchGroup,
  PrepToolStep,
  ResumePickerItem,
} from "@/types";
import { ApiError, consumeSSE, parseStructuredErrorResponse, request, resolveBackendUrl } from "@/lib/api/base";

export interface PrepStreamCallbacks {
  onToken: (token: string) => void;
  onSearchResults?: (groups: PrepSearchGroup[]) => void;
  /** 过程状态(如「正在分析问题…」),text 为空表示清除 */
  onStatus?: (text: string) => void;
  /** ReAct 工具步进(即时) */
  onToolStep?: (step: PrepToolStep) => void;
  /** Agent 请求用户弹窗选择 */
  onAskUser?: (question: string, options: string[]) => void;
}

export const agentService = {
  listResumes: () => request<ResumePickerItem[]>("/v1/prep/resumes"),
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
    request<Array<{ role: string; content: string }>>(
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
  ): Promise<{ token_usage: number }> => {
    const { onToken, onSearchResults, onStatus, onToolStep, onAskUser } = callbacks;
    const url = resolveBackendUrl(
      `/api/v1/prep/sessions/${sessionId}/message/stream`,
    );
    let res: Response;
    try {
      res = await fetch(url, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content }),
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
    await consumeSSE<PrepSSEEvent>(res, (event) => {
      if (event.type === "token" && typeof event.content === "string") {
        onToken(event.content);
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
      } else if (event.type === "done") {
        tokenUsage = event.token_usage;
      } else if (event.type === "error") {
        throw new ApiError(event.message || "流式输出失败", res.status);
      }
    });
    return { token_usage: tokenUsage };
  },
};

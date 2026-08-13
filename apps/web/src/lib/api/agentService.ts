/** 智能体服务客户端（对应后端 ``agent_service``：面试准备教练） */

import type {
  PrepMessageResponse,
  PrepSessionCreateResponse,
  PrepSSEEvent,
  PrepSearchGroup,
} from "@/types";
import { ApiError, consumeSSE, parseStructuredErrorResponse, request, resolveBackendUrl } from "@/lib/api/base";

export const agentService = {
  createPrepSession: (data: {
    resume_id?: number;
    target_role?: string;
    target_company?: string;
  }) =>
    request<PrepSessionCreateResponse>("/v1/prep/sessions", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  prepMessage: (sessionId: number, content: string) =>
    request<PrepMessageResponse>(`/v1/prep/sessions/${sessionId}/message`, {
      method: "POST",
      body: JSON.stringify({ content }),
    }),
  prepMessageStream: async (
    sessionId: number,
    content: string,
    onToken: (token: string) => void,
    onSearchResults?: (groups: PrepSearchGroup[]) => void,
  ): Promise<{ token_usage: number }> => {
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
      } else if (event.type === "search_results" && Array.isArray(event.groups)) {
        onSearchResults?.(event.groups);
      } else if (event.type === "done") {
        tokenUsage = event.token_usage;
      } else if (event.type === "error") {
        throw new ApiError(event.message || "流式输出失败", res.status);
      }
    });
    return { token_usage: tokenUsage };
  },
};

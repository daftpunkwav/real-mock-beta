/** 模拟面试域客户端（对应后端 ``interview_service``：面试 / 报告 / 成长 / 选项）
 *
 * 注意（微服务化预留）：本域在单进程聚合下跨域调用 api_service 的简历接口
 * （``listResumes`` 属 api 域）。将来服务拆分时，此依赖需改为显式聚合 base URL。
 */

import type {
  ChatMessage,
  FaceAnalysis,
  FinishInterviewResponse,
  GetReportResponse,
  GrowthRecord,
  InterviewConfig,
  InterviewReport,
  InterviewSession,
  Options,
  ReportSSEEvent,
  SendMessageResponse,
  StartInterviewResponse,
} from "@/types";
import { ApiError, consumeSSE, parseStructuredErrorResponse, request, resolveBackendUrl, LLM_HEAVY_TIMEOUT_MS } from "@/lib/api/base";

export const interviewService = {
  /* 选项 */
  getOptions: () => request<Options>("/v1/options"),

  /* 面试 */
  createSession: (config: InterviewConfig) =>
    request<InterviewSession>("/v1/interview/sessions", {
      method: "POST",
      body: JSON.stringify(config),
    }),
  listSessions: () => request<InterviewSession[]>("/v1/interview/sessions"),
  getSession: (id: number) =>
    request<InterviewSession>(`/v1/interview/sessions/${id}`),
  startInterview: (id: number) =>
    request<StartInterviewResponse>(`/v1/interview/sessions/${id}/start`, {
      method: "POST",
    }),
  sendMessage: (id: number, content: string, faceAnalysis?: FaceAnalysis, imageBase64?: string) =>
    request<SendMessageResponse>(`/v1/interview/sessions/${id}/message`, {
      method: "POST",
      body: JSON.stringify({
        content,
        face_analysis: faceAnalysis,
        image_base64: imageBase64,
      }),
    }),
  getMessages: (id: number) =>
    request<ChatMessage[]>(`/v1/interview/sessions/${id}/messages`),
  finishInterview: (id: number) =>
    request<FinishInterviewResponse>(`/v1/interview/sessions/${id}/finish`, {
      method: "POST",
      timeoutMs: LLM_HEAVY_TIMEOUT_MS,
    }),

  /* 报告 */
  getReport: (id: number) => request<GetReportResponse>(`/v1/reports/${id}`),
  /**
   * 流式生成并消费报告 SSE。
   * 触发后端按 token 分片推送，done 事件携带完整 InterviewReport。
   * 失败时抛 ApiError，调用方降级到 getReport 轮询。
   */
  getReportStream: async (
    id: number,
    onToken: (token: string) => void,
    signal?: AbortSignal,
  ): Promise<InterviewReport> => {
    const url = resolveBackendUrl(`/api/v1/reports/${id}/stream`);
    let res: Response;
    try {
      res = await fetch(url, {
        credentials: "include",
        signal,
      });
    } catch {
      throw new ApiError(`无法直连后端流式接口 ${url}`, 0);
    }
    if (!res.ok) {
      const error = await parseStructuredErrorResponse(res);
      throw new ApiError(error.message, res.status, error);
    }

    let finalReport: InterviewReport | null = null;
    await consumeSSE<ReportSSEEvent>(res, (event) => {
      if (event.type === "token" && typeof event.content === "string") {
        onToken(event.content);
      } else if (event.type === "done") {
        finalReport = event.report;
      } else if (event.type === "error") {
        throw new ApiError(event.message || "报告流式生成失败", res.status);
      }
    });
    if (!finalReport) throw new ApiError("报告流式响应未包含完整数据", 0);
    return finalReport;
  },

  /* 成长 */
  getGrowthHistory: () => request<GrowthRecord[]>("/v1/reports/growth/history"),
  getSystemInsights: () =>
    request<{
      company_session_counts: Record<string, number>;
      role_session_counts: Record<string, number>;
      avg_scores_by_company: Record<string, number | null>;
      followup_category_hits: Record<string, number>;
      tool_call_counts: Record<string, number>;
      recent_probes: { company?: string; role?: string; point?: string; session_id?: number }[];
      updated_at?: string | null;
      github_token_configured?: boolean;
      interview_tools_enabled?: boolean;
    }>("/v1/reports/growth/system-insights"),
};

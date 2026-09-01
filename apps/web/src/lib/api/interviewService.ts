/** 模拟面试域客户端（对应后端 ``interview_service``：面试 / 报告 / 成长 / 选项 / 简历摘要）。 */

import type {
  ChatMessage,
  FinishInterviewResponse,
  GetReportResponse,
  GrowthRecord,
  InterviewConfig,
  InterviewSession,
  Options,
  ResumePickerItem,
} from "@/types";
import { request, LLM_HEAVY_TIMEOUT_MS } from "@/lib/api/base";

export const interviewService = {
  /* 选项 */
  getOptions: () => request<Options>("/v1/options"),
  listResumes: () => request<ResumePickerItem[]>("/v1/interview/resumes"),

  /* 面试 */
  /** InterviewConfig + 可选 ai_overrides（三任务模型条目 + 思考强度） */
  createSessionWithAI: (
    config: InterviewConfig,
    ai?: {
      chat_profile_id?: number | null;
      stt_profile_id?: number | null;
      tts_profile_id?: number | null;
      reasoning_effort?: import("@/types").ReasoningEffort | null;
    } | null,
  ) =>
    request<InterviewSession>("/v1/interview/sessions", {
      method: "POST",
      body: JSON.stringify({ ...config, ai_overrides: ai ?? undefined }),
    }),
  listSessions: () => request<InterviewSession[]>("/v1/interview/sessions"),
  getSession: (id: number) =>
    request<InterviewSession>(`/v1/interview/sessions/${id}`),
  getMessages: (id: number) =>
    request<ChatMessage[]>(`/v1/interview/sessions/${id}/messages`),
  finishInterview: (id: number) =>
    request<FinishInterviewResponse>(`/v1/interview/sessions/${id}/finish`, {
      method: "POST",
      timeoutMs: LLM_HEAVY_TIMEOUT_MS,
    }),

  /* 报告 */
  getReport: (id: number) => request<GetReportResponse>(`/v1/reports/${id}`),

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

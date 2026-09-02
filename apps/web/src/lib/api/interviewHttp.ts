/** 模拟面试 / 报告 / 成长 REST 客户端（能力命名，非后端包名）。 */

import type {
  ChatMessage,
  FinishInterviewResponse,
  GetReportResponse,
  InterviewConfig,
  InterviewSession,
  Options,
  ResumePickerItem,
} from "@/lib/api/contract";
import type { GrowthRecord, ReasoningEffort } from "@/types";
import { request, LLM_HEAVY_TIMEOUT_MS } from "@/lib/api/base";

/** 成长域 system-insights（OpenAPI 未建模） */
export type SystemGrowthInsights = {
  company_session_counts: Record<string, number>;
  role_session_counts: Record<string, number>;
  avg_scores_by_company: Record<string, number | null>;
  followup_category_hits: Record<string, number>;
  tool_call_counts: Record<string, number>;
  recent_probes: {
    company?: string;
    role?: string;
    point?: string;
    session_id?: number;
  }[];
  updated_at?: string | null;
  github_token_configured?: boolean;
  interview_tools_enabled?: boolean;
};

export const interviewHttp = {
  getOptions: () => request<Options>("/v1/options"),
  listResumes: () => request<ResumePickerItem[]>("/v1/interview/resumes"),

  createSessionWithAI: (
    config: InterviewConfig,
    ai?: {
      chat_profile_id?: number | null;
      stt_profile_id?: number | null;
      tts_profile_id?: number | null;
      reasoning_effort?: ReasoningEffort | null;
    } | null,
  ) =>
    request<InterviewSession>("/v1/interview/sessions", {
      method: "POST",
      body: JSON.stringify({ ...config, ai_overrides: ai ?? undefined }),
    }),
  listSessions: () => request<InterviewSession[]>("/v1/interview/sessions"),
  getSession: (id: number) => request<InterviewSession>(`/v1/interview/sessions/${id}`),
  getMessages: (id: number) => request<ChatMessage[]>(`/v1/interview/sessions/${id}/messages`),
  finishInterview: (id: number) =>
    request<FinishInterviewResponse>(`/v1/interview/sessions/${id}/finish`, {
      method: "POST",
      timeoutMs: LLM_HEAVY_TIMEOUT_MS,
    }),

  getReport: (id: number) => request<GetReportResponse>(`/v1/reports/${id}`),

  getGrowthHistory: () => request<GrowthRecord[]>("/v1/growth/history"),
  getSystemInsights: () => request<SystemGrowthInsights>("/v1/growth/system-insights"),
};

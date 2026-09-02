/**
 * OpenAPI 生成契约 re-export（REST 单轨）。
 * 手写 WS / SSE 域类型仍见 `@/types/domains`。
 */

import type { components, paths } from "@/types/generated/api";

export type ApiPaths = paths;
export type ApiSchemas = components["schemas"];

/* api_service */
export type UserProfileResponse = components["schemas"]["UserProfileResponse"];
export type UserProfileUpdate = components["schemas"]["UserProfileUpdate"];
export type ResumeResponse = components["schemas"]["ResumeResponse"];
export type ResumeAnalysis = components["schemas"]["ResumeAnalysis"];
export type LLMTestResponse = components["schemas"]["LLMTestResponse"];

/* agent_service Prep REST */
export type PrepSessionSummary = components["schemas"]["PrepSessionSummary"];
export type PrepSessionCreateResponse = components["schemas"]["PrepSessionCreateResponse"];
export type PrepHistoryMessage = components["schemas"]["PrepHistoryMessage"];
export type PrepToolStep = components["schemas"]["PrepToolStep"];
export type PrepSearchHit = components["schemas"]["PrepSearchHit"];
export type PrepSearchGroup = components["schemas"]["PrepSearchGroup"];

/* interview_service REST */
export type InterviewSession = components["schemas"]["InterviewSessionResponse"];
export type Options = components["schemas"]["OptionsResponse"];
export type ResumePickerItem = components["schemas"]["ResumePickerItem"];
export type InterviewConfig = components["schemas"]["InterviewConfig"];
export type ChatMessage = components["schemas"]["ChatMessage"];
export type InterviewReport = components["schemas"]["InterviewReport"];
export type GetReportResponse = components["schemas"]["InterviewReportResponse"];
export type FinishInterviewResponse = components["schemas"]["FinishInterviewResponse"];

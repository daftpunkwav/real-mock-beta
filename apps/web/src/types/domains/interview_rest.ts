/** 面试 REST API 响应契约。 */

import type { ChatMessage, InterviewReport } from "./interview_core";

export interface StartInterviewResponse {
  message?: ChatMessage;
  current_phase: string;
}

export interface SendMessageResponse {
  message: ChatMessage;
  current_phase: string;
  is_complete: boolean;
  phases_remaining: string[];
}

export interface FinishInterviewResponse {
  session_id: number;
  status: string;
  overall_score?: number;
}

export interface GetReportResponse {
  session_id: number;
  report: InterviewReport;
  duration_minutes?: number;
  messages_count?: number;
}

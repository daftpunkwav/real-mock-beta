/** 面试 / 报告 / 成长 / SSE / WebSocket 事件类型。 */

import type { InterviewStyleId } from "./profile";

export interface InterviewConfig {
  role: string;
  level: string;
  company: string;
  workflow_type: string;
  personality: string;
  strictness: number;
  interview_style: InterviewStyleId;
  resume_id?: number | null;
  avatar_id?: string;
  scene_id?: string;
}

export interface InterviewSession {
  id: number;
  role: string;
  level: string;
  company: string;
  workflow_type: string;
  personality: string;
  strictness: number;
  interview_style: string;
  avatar_id?: string;
  scene_id?: string;
  status: string;
  current_phase: string;
  overall_score?: number;
  started_at?: string;
  ended_at?: string;
  created_at: string;
  access_token?: string | null;
}

export interface ChatMessage {
  role: "user" | "assistant" | "system";
  content: string;
  timestamp?: string;
}

export interface ScoreBreakdown {
  technical: number;
  communication: number;
  project_depth: number;
  problem_solving: number;
  presence?: number;
  politeness?: number;
  overall: number;
}

export interface InterviewReport {
  overall_score: number;
  score_breakdown: ScoreBreakdown;
  strengths: string[];
  weaknesses: string[];
  improvement_suggestions: string[];
  resume_suggestions?: string[];
  interview_suggestions?: string[];
  training_plan: string[];
  phase_summary: Record<string, string>;
  face_analysis_summary: string;
  presence_moments?: string[];
}

export interface GrowthRecord {
  id: number;
  session_id: number;
  weak_skills: string[];
  training_plan: string[];
  created_at: string;
}

/** 多模态输入 */
export interface FaceAnalysis {
  dominant_emotion?: string;
  emotion_scores?: Record<string, string>;
  eye_contact?: boolean;
  smile?: boolean;
  confidence?: number;
  timestamp_ms?: number;
  [extra: string]: unknown;
}

/* ── SSE 事件 ───────────────────────────────────── */

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

/* ── WebSocket 事件 ─────────────────────────────── */

export type TurnState = "IDLE" | "AI_SPEAKING" | "USER_SPEAKING" | "PROCESSING";

export type ServerEvent =
  | { type: "turn_state"; state: TurnState }
  | { type: "assistant_token"; token: string; phase?: string }
  | {
      type: "assistant_done";
      content: string;
      phase: string;
      emotion?: string;
      is_complete: boolean;
      audio_b64?: string;
      playback_generation?: number;
      /** 预计候选人作答秒数（turn 协议；0/缺省=未提供） */
      wait_seconds?: number;
      /** 本轮作答依据：resume | github | company_kb | none */
      sources?: string[];
    }
  | { type: "stt_partial"; text: string }
  | { type: "stt_final"; text: string }
  | {
      type: "tts_audio";
      data: string;
      mime?: string;
      sentence?: string;
      playback_generation?: number;
    }
  | { type: "tts_failed"; message: string }
  | { type: "tts_interrupted"; reason?: string; candidate_interrupts?: number; playback_generation?: number }
  | { type: "silence_nudge"; content: string; seq?: number; ai_interrupts?: number }
  | { type: "reference_hint_loading"; question: string }
  | { type: "reference_hint"; content: string; question: string }
  | { type: "phase_changed"; phase: string }
  | { type: "interview_complete"; session_id?: number; overall_score?: number | null; report_id?: number }
  | { type: "server_ping"; t: number }
  | {
      type: "info";
      message: string;
      fallback?: boolean;
      provider?: string;
      requested_provider?: string | null;
    }
  | SSEErrorEvent;

export type ClientEvent =
  | {
      type: "user_text";
      text: string;
      face_analysis?: FaceAnalysis;
      image_base64?: string;
    }
  | {
      type: "user_turn_end";
      pcm: string;
      sample_rate: number;
      text?: string;
      face_analysis?: FaceAnalysis;
      image_base64?: string;
    }
  | { type: "stt_text"; text: string }
  | { type: "silence_timeout" }
  | { type: "barge_in" }
  | { type: "request_hint"; question: string }
  | { type: "request_finish" }
  | { type: "vision_update"; face_analysis: FaceAnalysis }
  | { type: "tts_playback_done"; generation?: number }
  | { type: "pong"; t: number };

/* ── REST API 响应契约 ─────────────────────────── */

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

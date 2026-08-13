/** RealMock 前端类型定义 */

/* ====================================================================== */
/* 静态资源（GET /options 等）                                            */
/* ====================================================================== */

export interface LLMSettings {
  api_base: string;
  model: string;
  max_tokens: number;
  context_window: number;
  provider: string;
  protocol?: string;
  reasoning_effort?: string;
  supports_vision?: boolean;
  supports_audio?: boolean;
  stt_model?: string;
  tts_voice?: string;
  has_api_key: boolean;
  // 三阶段处理器
  speech_recognize_handler?: string;
  speech_recognize_mode?: string;
  asr_api_base?: string;
  asr_model?: string;
  asr_app_id?: string;
  asr_resource_id?: string;
  asr_app_key?: string;
  has_asr_api_key?: boolean;
  has_asr_api_secret?: boolean;
  has_asr_access_key?: boolean;
  speech_speak_handler?: string;
  speech_speak_mode?: string;
  tts_api_base?: string;
  tts_model?: string;
  has_tts_api_key?: boolean;
  updated_at?: string;
  /**
   * 仅在 settings 编辑态下使用,后端 ``LLMSettingsResponse`` 不会返回真实 key。
   * 写入时:留空或传 ``"keep"`` 表示不修改已有 key,新值会被后端 at-rest 加密。
   */
  api_key?: string;
  asr_api_key?: string;
  asr_api_secret?: string;
  asr_access_key?: string;
  tts_api_key?: string;
}

/** 写 LLM 设置时携带 ``api_key`` placeholder (``"keep"`` 表示不修改)。 */
export type LLMSettingsWrite = Omit<
  LLMSettings,
  | "has_api_key"
  | "has_asr_api_key"
  | "has_asr_api_secret"
  | "has_asr_access_key"
  | "has_tts_api_key"
  | "updated_at"
> & {
  api_key?: string;
  asr_api_key?: string;
  asr_api_secret?: string;
  asr_access_key?: string;
  tts_api_key?: string;
};

export type LLMProtocol = "openai_chat" | "anthropic_messages" | "openai_responses";

export interface StageModelCapabilities {
  supports_vision: boolean;
  supports_audio_input: boolean;
  supports_audio_output: boolean;
  supports_video_input: boolean;
}

export interface StageFallbackConfig {
  handler: string;
  mode: string;
}

export interface StageConfig {
  stage: string;
  provider: string;
  api_base: string;
  protocol: LLMProtocol;
  model: string;
  max_tokens: number;
  context_window: number;
  capabilities: StageModelCapabilities;
  fallback: StageFallbackConfig;
  extras: Record<string, unknown>;
  has_api_key: boolean;
  updated_at?: string;
  api_key?: string;
}

export interface StageConfigs {
  recognize: StageConfig;
  reason: StageConfig;
  speak: StageConfig;
  updated_at?: string;
}

export interface VoiceProviderOption {
  id: string;
  label: string;
  can_speech_recognize: boolean;
  can_interview_reason: boolean;
  can_speech_speak: boolean;
  recognize_via: "native_audio" | "transcribe_only" | "none";
  speak_via: "native_audio" | "tts_from_text" | "none";
  status: "ready" | "coming_soon";
  default_model?: string;
  default_api_base?: string;
  hint?: string;
}

export interface VoiceCatalog {
  reasoning: VoiceProviderOption[];
  recognize: VoiceProviderOption[];
  speak: VoiceProviderOption[];
}

export interface UserProfile {
  id: number;
  name: string;
  gender?: string;
  identity?: string;
  school?: string;
  major?: string;
  graduation_year?: string;
  job_direction: string;
  experience_years: string;
  work_years_detail?: string;
  current_company?: string;
  expected_salary?: string;
  self_intro?: string;
  tech_domains: string[];
  target_role: string;
  github_username?: string;
  portfolio_url?: string;
  linkedin_url?: string;
  city?: string;
  preferred_languages?: string;
  career_highlights?: string;
  open_to_remote?: string;
  notice_period?: string;
  education_level?: string;
  expected_city?: string;
  email?: string;
  phone?: string;
  certificates?: string;
  english_level?: string;
  signature_projects?: string;
  strengths?: string;
  weaknesses?: string;
  updated_at?: string;
}

export interface CandidateProfile {
  name: string;
  education: Record<string, string>[];
  work_experience: Record<string, string>[];
  skills: string[];
  projects: Record<string, string>[];
  summary: string;
}

export interface DimensionScore {
  score: number;
  comment?: string;
}

export interface RewriteExample {
  before: string;
  after: string;
}

export interface ResumeAnalysis {
  score: number;
  strengths: string[];
  weaknesses: string[];
  improvement_suggestions: string[];
  predicted_questions: string[];
  dimension_scores?: Record<string, DimensionScore | number>;
  ats_keywords?: string[];
  missing_keywords?: string[];
  project_deep_dive?: string[];
  red_flags?: string[];
  role_fit_summary?: string;
  seniority_estimate?: string;
  /** 兼容旧版字符串与新版 {before,after} */
  rewrite_examples?: Array<string | RewriteExample>;
  interview_risk_areas?: string[];
  overall_narrative?: string;
  layout_review?: string;
  typography_review?: string;
  content_review?: string;
  market_insights?: string[];
  search_queries_used?: string[];
}

export interface Resume {
  id: number;
  filename: string;
  file_type: string;
  parsed_profile: CandidateProfile;
  is_active?: boolean;
  score?: number | null;
  analysis?: ResumeAnalysis | Record<string, unknown>;
  created_at: string;
}

export interface CompanyInfo {
  id: string;
  name: string;
  style: string;
  focus_areas: string[];
  sample_questions: string[];
}

export interface Options {
  roles: string[];
  levels: string[];
  experience_years: string[];
  companies: CompanyInfo[];
  personalities: { id: string; name: string; description: string }[];
  interview_styles: { id: string; name: string; description: string }[];
  workflow_types: { id: string; name: string; phases: string[] }[];
  /** 阶段 id → 中文名（权威来源：后端 workflows） */
  phase_labels?: Record<string, string>;
  avatars?: { id: string; name: string; voice?: string }[];
  scenes?: { id: string; name: string }[];
  tts_voices?: { id: string; name: string }[];
  /** 后端配置的静默追问触发秒数，前端据此设置计时器 */
  silence_nudge_seconds?: number;
}

/** 与后端 ``InterviewStyle`` 枚举保持一致 */
export type InterviewStyleId = "guided" | "deep_dive" | "continuous" | "challenging";

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
  /** 仅 create 历史兼容字段；现经 HttpOnly Cookie 下发，响应体通常为 null */
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

/* ====================================================================== */
/* 多模态输入                                                              */
/* ====================================================================== */

export interface FaceAnalysis {
  dominant_emotion?: string;
  emotion_scores?: Record<string, number>;
  eye_contact?: boolean;
  smile?: boolean;
  confidence?: number;
  /** 时间戳相对值（毫秒，距录像开始） */
  timestamp_ms?: number;
  [extra: string]: unknown;
}

/* ====================================================================== */
/* SSE 事件（面试准备 / 报告生成）                                          */
/* ====================================================================== */

export interface SSEErrorEvent {
  type: "error";
  message: string;
  /** 业务错误码（A/B/C 三分 + 域 + 序号，如 C0001）；旧帧缺失时由前端按 B0001 兜底 */
  code?: string;
  /** 是否可重试；用于前端展示"重试"按钮 */
  retryable?: boolean;
}

/** 通用 SSE envelope，使用 discriminated union 保留强类型。 */
export interface PrepSearchHit {
  title: string;
  url: string;
  snippet: string;
}

export interface PrepSearchGroup {
  query: string;
  results: PrepSearchHit[];
}

export type PrepSSEEvent =
  | { type: "token"; content: string }
  | { type: "search_results"; groups: PrepSearchGroup[] }
  | { type: "done"; token_usage: number }
  | SSEErrorEvent;

export type ReportSSEEvent =
  | { type: "token"; content: string }
  | { type: "done"; report: InterviewReport; token_usage: number }
  | SSEErrorEvent;

/* ====================================================================== */
/* WebSocket 事件（实时面试）                                              */
/* ====================================================================== */

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
  | { type: "silence_nudge"; content: string; ai_interrupts?: number }
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

/* ====================================================================== */
/* REST API 响应契约                                                       */
/* ====================================================================== */

export interface StartInterviewResponse {
  message?: ChatMessage;
  current_phase: string;
}

export interface SendMessageResponse {
  message: ChatMessage;
  current_phase: string;
  is_complete: boolean;
  phases_remaining: number;
}

export interface FinishInterviewResponse {
  session_id: number;
  status: string;
  overall_score?: number;
}

export interface ResumeActivateResponse {
  id: number;
  is_active: boolean;
}

export interface GetReportResponse {
  session_id: number;
  report: InterviewReport;
  duration_minutes?: number;
  messages_count?: number;
}

export interface PrepSessionCreateResponse {
  id: number;
  access_token?: string | null;
}

export interface PrepMessageResponse {
  reply: string;
  token_usage: number;
}

export interface LLMTestResponse {
  success: boolean;
  message: string;
  model?: string | null;
  transcript?: string | null;
  audio_base64?: string | null;
  fallback?: string | null;
}

/* ====================================================================== */
/* 错误响应统一 envelope（与后端 ``app.schemas.APIError`` 一一对齐）        */
/* ====================================================================== */

export interface ApiErrorBody {
  /** 业务错误码（如 A1005 / C0001）；旧 envelope 缺失时由前端兜底 */
  code: string;
  /** 中文默认文案，前端直接展示 */
  message: string;
  /** 中文处置建议（hint）；可作为第二行小字展示 */
  hint?: string;
  /** 是否可重试；用于展示"重试"按钮 */
  retryable?: boolean;
  /** 服务端 trace_id；用户反馈时可携带，便于日志检索 */
  trace_id?: string;
}

export interface ApiErrorEnvelope {
  /** 旧字段，向后兼容 */
  detail?: string;
  /** 新统一字段 */
  error?: ApiErrorBody;
}

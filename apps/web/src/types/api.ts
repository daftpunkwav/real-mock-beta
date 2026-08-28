/** LLM / 处理器配置 / 语音目录类型。 */

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
  api_key?: string;
  asr_api_key?: string;
  asr_api_secret?: string;
  asr_access_key?: string;
  tts_api_key?: string;
}

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

export interface LLMTestResponse {
  success: boolean;
  message: string;
  model?: string | null;
  transcript?: string | null;
  audio_base64?: string | null;
  fallback?: string | null;
}

/** 错误响应统一 envelope */
export interface ApiErrorBody {
  code: string;
  message: string;
  hint?: string;
  retryable?: boolean;
  trace_id?: string;
}

export interface ApiErrorEnvelope {
  detail?: string;
  error?: ApiErrorBody;
}

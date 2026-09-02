"""LLM / 处理器三阶段配置契约。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from shared.core.constants import DEFAULT_LLM_PROTOCOL


class StageModelCapability(BaseModel):
    """单个模型能力开关。"""

    supports_vision: bool = False
    supports_audio_input: bool = False
    supports_audio_output: bool = False
    supports_video_input: bool = False


class StageFallbackConfig(BaseModel):
    """阶段降级处理配置。"""

    handler: str = ""
    mode: str = ""


class StageConfigUpdate(BaseModel):
    """单个阶段处理器保存请求。"""

    provider: str = ""
    api_base: str = ""
    api_key: str = ""
    protocol: Literal["openai_chat", "anthropic_messages", "openai_responses"] = "openai_chat"
    model: str = ""
    max_tokens: int = Field(default=4096, ge=1)
    context_window: int = Field(default=128000, ge=1)
    capabilities: StageModelCapability = Field(default_factory=StageModelCapability)
    fallback: StageFallbackConfig = Field(default_factory=StageFallbackConfig)
    extras: dict[str, Any] = Field(default_factory=dict)


class StageConfigResponse(BaseModel):
    """单个阶段处理器返回。"""

    stage: str
    provider: str
    api_base: str
    protocol: str
    model: str
    max_tokens: int
    context_window: int
    capabilities: StageModelCapability
    fallback: StageFallbackConfig
    extras: dict[str, Any]
    has_api_key: bool
    updated_at: datetime | None = None


class StageConfigsResponse(BaseModel):
    """新版三阶段配置返回。"""

    recognize: StageConfigResponse
    reason: StageConfigResponse
    speak: StageConfigResponse
    updated_at: datetime | None = None


class LLMSettingsUpdate(BaseModel):
    """DEPRECATED: 兼容旧版三阶段统一保存；内部会拆到 stage_configs。将在 v2.0 移除。"""

    api_base: str
    api_key: str
    model: str
    max_tokens: int = 4096
    context_window: int = 128000
    provider: str = ""
    protocol: Literal["openai_chat", "anthropic_messages", "openai_responses"] = "openai_chat"
    reasoning_effort: str = "medium"
    supports_vision: bool = True
    supports_audio: bool = False
    stt_model: str = "whisper-1"
    tts_voice: str = "zh-CN-XiaoxiaoNeural"
    # 三阶段指派
    speech_recognize_handler: str = "local"
    speech_recognize_mode: str = "transcribe"
    asr_api_base: str = ""
    asr_api_key: str = ""
    asr_model: str = ""
    asr_app_id: str = ""
    asr_api_secret: str = ""
    asr_access_key: str = ""
    asr_resource_id: str = ""
    asr_app_key: str = ""
    speech_speak_handler: str = "edge"
    speech_speak_mode: str = "tts_from_text"
    tts_api_base: str = ""
    tts_api_key: str = ""
    tts_model: str = ""


class LLMSettingsResponse(BaseModel):
    api_base: str
    model: str
    max_tokens: int
    context_window: int
    provider: str
    protocol: str = DEFAULT_LLM_PROTOCOL
    reasoning_effort: str = "medium"
    supports_vision: bool = True
    supports_audio: bool = False
    stt_model: str = "whisper-1"
    tts_voice: str = "zh-CN-XiaoxiaoNeural"
    has_api_key: bool
    # 三阶段指派（密钥仅返回 has_* 布尔）
    speech_recognize_handler: str = "local"
    speech_recognize_mode: str = "transcribe"
    asr_api_base: str = ""
    asr_model: str = ""
    asr_app_id: str = ""
    asr_resource_id: str = ""
    asr_app_key: str = ""
    has_asr_api_key: bool = False
    has_asr_api_secret: bool = False
    has_asr_access_key: bool = False
    speech_speak_handler: str = "edge"
    speech_speak_mode: str = "tts_from_text"
    tts_api_base: str = ""
    tts_model: str = ""
    has_tts_api_key: bool = False
    updated_at: datetime | None = None


class LLMTestResponse(BaseModel):
    success: bool
    message: str
    model: str | None = None
    transcript: str | None = None
    audio_base64: str | None = None
    fallback: str | None = None
    latency_ms: int | None = None


class StageTestRequest(BaseModel):
    """可选覆盖；默认用库内已保存配置。"""

    stage: Literal["recognize", "reason", "speak"] | None = None

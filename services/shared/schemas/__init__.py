"""跨服务共享契约（Pydantic 模型）。

归属规则：只放被两个及以上服务（或服务与语音/LLM 能力层）共用的类型——
错误 envelope、处理器配置、LLM 设置、企业信息。业务专属类型按域分属各服务。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from shared.core.constants import DEFAULT_LLM_PROTOCOL


# ── LLM / 处理器配置契约 ──────────────────────────────────────────

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


# ── 错误响应统一 envelope ────────────────────────────────────────


class ErrorBody(BaseModel):
    code: str
    message: str
    trace_id: str = ""


class APIError(BaseModel):
    """统一错误响应形状，与聚合入口的 envelope 一一对齐。"""

    model_config = {"extra": "forbid"}

    detail: str | None = None
    error: ErrorBody | None = None


# ── 企业信息契约 ──────────────────────────────────────────


class CompanyInfo(BaseModel):
    id: str
    name: str
    style: str
    focus_areas: list[str]
    sample_questions: list[str]


class CandidateProfile(BaseModel):
    """结构化候选人简历档案。

    由 api_service 简历解析产出、interview 面试 Agent 读取构建候选人画像，
    两域共享，故置于 shared 契约层。
    """

    name: str = ""
    education: list[dict[str, Any]] = Field(default_factory=list)
    work_experience: list[dict[str, Any]] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    projects: list[dict[str, Any]] = Field(default_factory=list)
    summary: str = ""


class ResumePickerItem(BaseModel):
    """简历下拉只读摘要：prep / interview 配置页共用，不含解析正文与深度评价。"""

    id: int
    filename: str
    is_active: bool = False
    score: int | None = None


__all__ = [
    "APIError",
    "CandidateProfile",
    "CompanyInfo",
    "ErrorBody",
    "LLMSettingsResponse",
    "LLMSettingsUpdate",
    "LLMTestResponse",
    "ResumePickerItem",
    "StageConfigResponse",
    "StageConfigUpdate",
    "StageConfigsResponse",
    "StageFallbackConfig",
    "StageModelCapability",
    "StageTestRequest",
]

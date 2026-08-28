"""基础设施/处理器配置 ORM 模型。

StageConfig / LLMSettings 是跨服务共享的处理器配置表，不属于任何业务域。
从 ``shared.models`` 提取到此处，``shared.models`` 保留 re-export 以兼容。
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from shared.core.constants import DEFAULT_LLM_PROTOCOL
from shared.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class StageConfig(Base):
    """三阶段处理器独立配置：recognize / reason / speak。

    每条记录对应一个阶段，支持自定义供应商、API 格式、模型能力等。
    """

    __tablename__ = "stage_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stage: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    provider: Mapped[str] = mapped_column(String(100), default="")
    api_base: Mapped[str] = mapped_column(String(500), default="")
    api_key: Mapped[str] = mapped_column(String(500), default="")
    protocol: Mapped[str] = mapped_column(String(50), default=DEFAULT_LLM_PROTOCOL)
    model: Mapped[str] = mapped_column(String(100), default="")
    max_tokens: Mapped[int] = mapped_column(Integer, default=4096)
    context_window: Mapped[int] = mapped_column(Integer, default=128000)
    supports_vision: Mapped[bool] = mapped_column(Boolean, default=False)
    supports_audio_input: Mapped[bool] = mapped_column(Boolean, default=False)
    supports_audio_output: Mapped[bool] = mapped_column(Boolean, default=False)
    supports_video_input: Mapped[bool] = mapped_column(Boolean, default=False)
    fallback_handler: Mapped[str] = mapped_column(String(100), default="")
    fallback_mode: Mapped[str] = mapped_column(String(30), default="")
    extras: Mapped[str] = mapped_column(Text, default="{}")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)


class LLMSettings(Base):
    """BYOK LLM 配置（保留做兼容读；新逻辑优先使用 stage_configs）。"""

    __tablename__ = "llm_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    api_base: Mapped[str] = mapped_column(String(500), default="")
    api_key: Mapped[str] = mapped_column(String(500), default="")
    model: Mapped[str] = mapped_column(String(100), default="")
    max_tokens: Mapped[int] = mapped_column(Integer, default=4096)
    context_window: Mapped[int] = mapped_column(Integer, default=128000)
    provider: Mapped[str] = mapped_column(String(50), default="")
    protocol: Mapped[str] = mapped_column(String(50), default=DEFAULT_LLM_PROTOCOL)
    reasoning_effort: Mapped[str] = mapped_column(String(20), default="medium")
    supports_vision: Mapped[bool] = mapped_column(Boolean, default=True)
    supports_audio: Mapped[bool] = mapped_column(Boolean, default=False)
    # 兼容旧字段：识别模型 / Edge 音色
    stt_model: Mapped[str] = mapped_column(String(50), default="whisper-1")
    tts_voice: Mapped[str] = mapped_column(String(100), default="zh-CN-XiaoxiaoNeural")
    # ── 三阶段处理器指派 ──────────────────────────────
    # 阶段1 语音识别
    speech_recognize_handler: Mapped[str] = mapped_column(String(50), default="local")
    speech_recognize_mode: Mapped[str] = mapped_column(String(30), default="transcribe")
    asr_api_base: Mapped[str] = mapped_column(String(500), default="")
    asr_api_key: Mapped[str] = mapped_column(String(500), default="")
    asr_model: Mapped[str] = mapped_column(String(100), default="")
    asr_app_id: Mapped[str] = mapped_column(String(100), default="")
    asr_api_secret: Mapped[str] = mapped_column(String(500), default="")
    asr_access_key: Mapped[str] = mapped_column(String(500), default="")
    asr_resource_id: Mapped[str] = mapped_column(String(100), default="")
    asr_app_key: Mapped[str] = mapped_column(String(100), default="")
    # 阶段3 语音输出（阶段2 复用上方 provider/api_* / model）
    speech_speak_handler: Mapped[str] = mapped_column(String(50), default="edge")
    speech_speak_mode: Mapped[str] = mapped_column(String(30), default="tts_from_text")
    tts_api_base: Mapped[str] = mapped_column(String(500), default="")
    tts_api_key: Mapped[str] = mapped_column(String(500), default="")
    tts_model: Mapped[str] = mapped_column(String(100), default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)


__all__ = ["LLMSettings", "StageConfig"]

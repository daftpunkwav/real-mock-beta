"""旧版 /llm 聚合读写（DEPRECATED 兼容层，将在 v2.0 移除）。

内部仍从 stage_configs 聚合三阶段字段，与新版 /stages 共享同一份数据；
密钥不回显明文（``has_api_key`` 一类布尔标记）。
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from shared.core.constants import PipelineStage
from shared.schemas import (
    LLMSettingsResponse,
    LLMSettingsUpdate,
    StageFallbackConfig,
    StageModelCapability,
    StageConfigUpdate,
)
from shared.services.pipeline_config import (
    get_stage_config_map,
    get_stage_config_for_runtime,
    update_stage_config,
)
from api_service.services.settings_validation import safe_base


def read_legacy_llm_settings(db: Session) -> LLMSettingsResponse:
    """从 stage_configs 聚合旧版设置响应（reason/recognize/speak 三阶段）。"""
    cfg_map = get_stage_config_map(db)
    reason = cfg_map.get("reason", {})
    recognize = cfg_map.get("recognize", {})
    speak = cfg_map.get("speak", {})
    rec_extras = recognize.get("extras") or {}
    speak_extras = speak.get("extras") or {}
    rec_runtime = get_stage_config_for_runtime(db, PipelineStage.RECOGNIZE.value)
    rec_runtime_extras = rec_runtime.get("extras") or {}
    return LLMSettingsResponse(
        api_base=reason.get("api_base") or "",
        model=reason.get("model") or "",
        max_tokens=reason.get("max_tokens", 4096),
        context_window=reason.get("context_window", 128000),
        provider=reason.get("provider") or "",
        protocol=reason.get("protocol") or "openai_chat",
        reasoning_effort="medium",
        supports_vision=reason.get("capabilities", {}).get("supports_vision", True),
        supports_audio=reason.get("capabilities", {}).get("supports_audio_output", False),
        stt_model=recognize.get("model") or "",
        tts_voice=speak_extras.get("tts_voice") or "zh-CN-XiaoxiaoNeural",
        has_api_key=reason.get("has_api_key", False),
        speech_recognize_handler=recognize.get("provider") or "local",
        speech_recognize_mode=rec_extras.get("speech_recognize_mode") or "transcribe",
        asr_api_base=recognize.get("api_base") or "",
        asr_model=recognize.get("model") or "",
        asr_app_id=rec_extras.get("asr_app_id") or "",
        asr_resource_id=rec_extras.get("asr_resource_id") or "",
        asr_app_key=rec_extras.get("asr_app_key") or "",
        has_asr_api_key=recognize.get("has_api_key", False),
        has_asr_api_secret=bool(rec_runtime_extras.get("asr_api_secret")),
        has_asr_access_key=bool(rec_runtime_extras.get("asr_access_key")),
        speech_speak_handler=speak.get("provider") or "edge",
        speech_speak_mode=speak_extras.get("speech_speak_mode") or "tts_from_text",
        tts_api_base=speak.get("api_base") or "",
        tts_model=speak.get("model") or "",
        has_tts_api_key=speak.get("has_api_key", False),
        updated_at=reason.get("updated_at"),
    )


def write_legacy_llm_settings(db: Session, body: LLMSettingsUpdate) -> LLMSettingsResponse:
    """旧版统一保存：拆分到 stage_configs，保存后聚合返回。"""
    safe_base(body.api_base, label="LLM API")
    safe_base(body.asr_api_base, label="ASR API")
    safe_base(body.tts_api_base, label="TTS API")

    update_stage_config(
        db,
        PipelineStage.REASON,
        StageConfigUpdate(
            provider=body.provider,
            api_base=body.api_base,
            api_key=body.api_key,
            protocol=body.protocol,
            model=body.model,
            max_tokens=body.max_tokens,
            context_window=body.context_window,
            capabilities=StageModelCapability(
                supports_vision=body.supports_vision,
                supports_audio_output=body.supports_audio,
            ),
            fallback=StageFallbackConfig(handler="", mode=""),
            extras={},
        ),
    )
    update_stage_config(
        db,
        PipelineStage.RECOGNIZE,
        StageConfigUpdate(
            provider=body.speech_recognize_handler,
            api_base=body.asr_api_base,
            api_key=body.asr_api_key,
            protocol="openai_chat",
            model=body.asr_model or body.stt_model,
            max_tokens=4096,
            context_window=8192,
            capabilities=StageModelCapability(supports_audio_input=True),
            fallback=StageFallbackConfig(handler="local", mode="transcribe"),
            extras={
                "speech_recognize_mode": body.speech_recognize_mode,
                "asr_app_id": body.asr_app_id,
                "asr_api_secret": body.asr_api_secret,
                "asr_access_key": body.asr_access_key,
                "asr_resource_id": body.asr_resource_id,
                "asr_app_key": body.asr_app_key,
            },
        ),
    )
    update_stage_config(
        db,
        PipelineStage.SPEAK,
        StageConfigUpdate(
            provider=body.speech_speak_handler,
            api_base=body.tts_api_base,
            api_key=body.tts_api_key,
            protocol="openai_chat",
            model=body.tts_model,
            max_tokens=8192,
            context_window=8192,
            capabilities=StageModelCapability(supports_audio_output=True),
            fallback=StageFallbackConfig(handler="edge", mode="tts_from_text"),
            extras={
                "speech_speak_mode": body.speech_speak_mode,
                "tts_voice": body.tts_voice,
            },
        ),
    )
    return read_legacy_llm_settings(db)

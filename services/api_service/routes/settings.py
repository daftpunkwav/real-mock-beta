"""BYOK 三处理器设置 API。

安全要点：

- 更新 ``api_base`` 时校验 URL（防 SSRF）；
- 密钥入库前 AES-256-GCM 加密；
- 识别凭证与思考 Key 分离，禁止静默混用。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from shared.config import get_settings
from shared.core.constants import DEFAULT_LLM_PROTOCOL, DEFAULT_LLM_RATE_LIMIT_PER_MINUTE, PipelineStage
from shared.core.errors import ApiBusinessError, get_spec, raise_error
from shared.core.local_only import require_local_peer
from shared.core.ratelimit import rate_limit_dep
from shared.core.security import is_safe_http_url
from shared.database import get_db
from shared.schemas import (
    LLMSettingsResponse,
    LLMSettingsUpdate,
    LLMTestResponse,
    StageFallbackConfig,
    StageModelCapability,
    StageConfigResponse,
    StageConfigsResponse,
    StageConfigUpdate,
)
from shared.capabilities.voice.config.catalog import catalog_payload, find_provider
from shared.services.pipeline_config import (
    get_stage_config_for_runtime,
    get_stage_config_map,
    stage_to_response,
    update_stage_config,
)
from api_service.services.stage_tests import test_recognize, test_reason, test_speak

router = APIRouter(dependencies=[Depends(require_local_peer)])


def _safe_base(url: str, *, label: str) -> None:
    if not (url or "").strip():
        return
    settings = get_settings()
    allow_local = bool(settings.allow_local_llm)
    require_https = bool(settings.is_prod)
    if not is_safe_http_url(url, allow_local=allow_local, require_https=require_https):
        raise ApiBusinessError(
            get_spec("A0007"),
            message=(
                f"{label} 地址不安全，"
                + (
                    "生产环境仅允许 https 公网地址。"
                    if require_https
                    else "仅允许 http(s) 公网地址。"
                )
                + "若需本地服务，请设置 ALLOW_LOCAL_LLM=true（仅非 prod）"
            ),
        )


def _validate_stage_config(stage: str, data: StageConfigUpdate) -> None:
    """校验单个阶段的 provider 选择是否与模式匹配。"""
    if stage == PipelineStage.RECOGNIZE:
        meta = find_provider("recognize", data.provider)
        if meta and meta.get("status") == "coming_soon":
            raise ApiBusinessError(get_spec("A4003"), message="识别处理者尚未接通")
    elif stage == PipelineStage.REASON:
        if data.provider in ("openai_compat", "xfyun", "volcengine", "aliyun", "tencent", "baidu", "local", "edge", "minimax_speech", "none", "mimo_audio"):
            raise ApiBusinessError(
                get_spec("A4001"),
                message="面试思考处理者必须是文本 LLM，不能选择仅 ASR/仅 TTS 供应商",
            )
        meta = find_provider("reasoning", data.provider)
        if meta and not meta.get("can_interview_reason") and meta.get("status") != "coming_soon":
            raise_error("A4001")
    elif stage == PipelineStage.SPEAK:
        meta = find_provider("speak", data.provider)
        if meta and meta.get("status") == "coming_soon":
            raise ApiBusinessError(get_spec("A4003"), message="播报处理者尚未接通")


@router.get("/catalog")
def get_voice_catalog() -> dict[str, Any]:
    """三阶段供应商能力目录。"""
    return catalog_payload()


@router.get("/llm", response_model=LLMSettingsResponse)
def get_llm_settings(db: Session = Depends(get_db)):
    """兼容旧版设置读取（内部仍从 stage_configs 聚合）。"""
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
        protocol=reason.get("protocol") or DEFAULT_LLM_PROTOCOL,
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


@router.put("/llm", response_model=LLMSettingsResponse)
def update_llm_settings(body: LLMSettingsUpdate, db: Session = Depends(get_db)):
    """兼容旧版统一保存：拆分到 stage_configs。

    URL 安全校验使用 ``allow_local_llm``，而不是开发环境字符串判断。
    """
    _safe_base(body.api_base, label="LLM API")
    _safe_base(body.asr_api_base, label="ASR API")
    _safe_base(body.tts_api_base, label="TTS API")

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
    return get_llm_settings(db)


@router.get("/stages", response_model=StageConfigsResponse)
def get_stage_configs(db: Session = Depends(get_db)):
    """新版三阶段配置读取。"""
    cfg_map = get_stage_config_map(db)
    return StageConfigsResponse(
        recognize=StageConfigResponse(**cfg_map["recognize"]),
        reason=StageConfigResponse(**cfg_map["reason"]),
        speak=StageConfigResponse(**cfg_map["speak"]),
        updated_at=cfg_map["reason"].get("updated_at"),
    )


@router.put("/stages/{stage}", response_model=StageConfigResponse)
def update_stage(
    stage: str,
    body: StageConfigUpdate,
    db: Session = Depends(get_db),
):
    """新版单阶段配置保存。"""
    stage = (stage or "").strip().lower()
    if stage not in (PipelineStage.RECOGNIZE, PipelineStage.REASON, PipelineStage.SPEAK):
        raise_error("A4004")

    _safe_base(body.api_base, label=f"{stage} API")
    _validate_stage_config(stage, body)

    row = update_stage_config(db, stage, body)
    return StageConfigResponse(**stage_to_response(row))


@router.post(
    "/llm/test",
    response_model=LLMTestResponse,
    dependencies=[Depends(rate_limit_dep(key="llm", limit=DEFAULT_LLM_RATE_LIMIT_PER_MINUTE))],
)
async def test_llm_connection(db: Session = Depends(get_db)):
    """兼容旧入口：等同于测试「面试思考」阶段，客户端遵循 ``allow_local_llm``。"""
    result = await test_reason(db)
    return LLMTestResponse(
        success=bool(result.get("success")),
        message=str(result.get("message") or ""),
        model=result.get("model"),
        transcript=result.get("transcript"),
        fallback=result.get("fallback"),
    )


@router.post(
    "/test/{stage}",
    response_model=LLMTestResponse,
    dependencies=[Depends(rate_limit_dep(key="llm", limit=DEFAULT_LLM_RATE_LIMIT_PER_MINUTE))],
)
async def test_pipeline_stage(stage: str, db: Session = Depends(get_db)):
    """三阶段连通性测试：recognize | reason | speak。"""
    stage = (stage or "").strip().lower()
    if stage == "recognize":
        result = await test_recognize(db)
    elif stage in ("reason", "reasoning", "llm"):
        result = await test_reason(db)
    elif stage in ("speak", "tts"):
        result = await test_speak(db)
    else:
        raise_error("A4004")

    return LLMTestResponse(
        success=bool(result.get("success")),
        message=str(result.get("message") or ""),
        model=result.get("model"),
        transcript=result.get("transcript"),
        audio_base64=result.get("audio_base64"),
        fallback=result.get("fallback"),
    )

"""从 LLMSettings 行构建三阶段运行时凭证。"""

from __future__ import annotations

from sqlalchemy.orm import Session

from shared.core.secrets import decrypt_secret
from shared.models import LLMSettings
from shared.capabilities.voice.stt.base import SttCredentials
from shared.capabilities.voice.tts import TtsCredentials
from shared.capabilities.voice.config.catalog import find_provider


def _g(row: LLMSettings, name: str, default: str = "") -> str:
    return str(getattr(row, name, default) or default)


def _dec(row: LLMSettings, name: str) -> str:
    """解密字段；``enc:*`` 密文解密失败时抛错，不回退原文。"""
    raw = getattr(row, name, None) or ""
    if not raw:
        return ""
    text = str(raw)
    # 明文兼容旧数据：非加密前缀直接返回
    if not text.startswith("enc:"):
        return text
    try:
        return decrypt_secret(text) or ""
    except Exception as e:
        raise ValueError(
            f"语音凭证字段 {name} 解密失败，请到设置页重新保存密钥"
        ) from e


def load_settings_row(db: Session) -> LLMSettings | None:
    return db.query(LLMSettings).filter(LLMSettings.id == 1).first()


def build_stt_credentials(row: LLMSettings | None, db: Session | None = None) -> SttCredentials:
    """构建独立识别凭证；新配置优先，绝不回落思考 Key。"""
    if db is not None:
        from shared.services.pipeline_config import get_stage_config_for_runtime

        cfg = get_stage_config_for_runtime(db, "recognize")
        extras = cfg.get("extras") or {}
        provider = cfg.get("provider") or (
            "custom" if cfg.get("api_base") and cfg.get("api_key") else "local"
        )
        return SttCredentials(
            provider=provider,
            protocol=cfg.get("protocol") or "openai_chat",
            api_base=cfg.get("api_base") or "",
            api_key=cfg.get("api_key") or "",
            model=cfg.get("model") or "base",
            app_id=extras.get("asr_app_id") or "",
            api_secret=extras.get("asr_api_secret") or "",
            access_key=extras.get("asr_access_key") or "",
            resource_id=extras.get("asr_resource_id") or "",
            app_key=extras.get("asr_app_key") or "",
            fallback_handler=cfg.get("fallback_handler") or "local",
            fallback_mode=cfg.get("fallback_mode") or "transcribe",
        )
    if not row:
        return SttCredentials(provider="local", model="base")

    handler = _g(row, "speech_recognize_handler", "local") or "local"
    mode = _g(row, "speech_recognize_mode", "transcribe")
    meta = find_provider("recognize", handler)

    # native_audio 未接通时运行时按 transcribe + local/openai 处理由 router 负责
    if mode == "native_audio" and meta and meta.get("status") == "coming_soon":
        handler = "local"

    model = _g(row, "asr_model") or _g(row, "stt_model", "base")
    return SttCredentials(
        provider=handler,
        protocol="openai_chat",
        api_base=_g(row, "asr_api_base"),
        api_key=_dec(row, "asr_api_key"),
        model=model,
        app_id=_g(row, "asr_app_id"),
        api_secret=_dec(row, "asr_api_secret"),
        access_key=_dec(row, "asr_access_key"),
        resource_id=_g(row, "asr_resource_id"),
        app_key=_g(row, "asr_app_key"),
        fallback_handler="local",
        fallback_mode="transcribe",
    )


def build_tts_credentials(row: LLMSettings | None, db: Session | None = None) -> TtsCredentials:
    """构建独立播报凭证；新配置优先。"""
    if db is not None:
        from shared.services.pipeline_config import get_stage_config_for_runtime

        cfg = get_stage_config_for_runtime(db, "speak")
        extras = cfg.get("extras") or {}
        handler = cfg.get("provider") or (
            "custom" if cfg.get("api_base") and cfg.get("api_key") else "edge"
        )
        return TtsCredentials(
            handler=handler,
            mode=extras.get("speech_speak_mode") or "tts_from_text",
            protocol=cfg.get("protocol") or "openai_chat",
            api_base=cfg.get("api_base") or "",
            api_key=cfg.get("api_key") or "",
            model=cfg.get("model") or "",
            voice=extras.get("tts_voice")
            or ("zh-CN-XiaoxiaoNeural" if handler == "edge" else "mimo_default"),
            fallback_handler=cfg.get("fallback_handler") or "edge",
            fallback_mode=cfg.get("fallback_mode") or "tts_from_text",
        )
    if not row:
        return TtsCredentials(handler="edge", voice="zh-CN-XiaoxiaoNeural")

    handler = _g(row, "speech_speak_handler", "edge") or "edge"
    mode = _g(row, "speech_speak_mode", "tts_from_text") or "tts_from_text"
    tts_key = _dec(row, "tts_api_key")
    # MiniMax Speech 可复用思考 Key（同一家），但 ASR 绝不复用
    if handler == "minimax_speech" and not tts_key:
        tts_key = _dec(row, "api_key")
    return TtsCredentials(
        handler=handler,
        mode=mode,
        protocol="openai_chat",
        api_base=_g(row, "tts_api_base") or "https://api.minimaxi.com/v1",
        api_key=tts_key,
        model=_g(row, "tts_model") or "speech-2.8-hd",
        voice=_g(row, "tts_voice", "zh-CN-XiaoxiaoNeural"),
    )

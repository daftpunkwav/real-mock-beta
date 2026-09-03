"""STT 供应商路由：按 handler id 分发，失败可回退本地 Whisper。"""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace

from shared.capabilities.voice.stt.aliyun import AliyunProvider
from shared.capabilities.voice.stt.baidu import BaiduProvider
from shared.capabilities.voice.stt.base import SttCredentials, SttProvider
from shared.capabilities.voice.stt.local import LocalWhisperProvider
from shared.capabilities.voice.stt.openai_compat import MimoAudioProvider, OpenAICompatProvider
from shared.capabilities.voice.stt.tencent import TencentProvider
from shared.capabilities.voice.stt.volcengine import VolcengineProvider
from shared.capabilities.voice.stt.xfyun import XfyunProvider
from shared.capabilities.voice.config.catalog import find_provider

logger = logging.getLogger(__name__)

_PROVIDERS: dict[str, SttProvider] = {
    "openai_compat": OpenAICompatProvider(),
    "mimo_audio": MimoAudioProvider(),
    "local": LocalWhisperProvider(),
    "xfyun": XfyunProvider(),
    "volcengine": VolcengineProvider(),
    "aliyun": AliyunProvider(),
    "tencent": TencentProvider(),
    "baidu": BaiduProvider(),
}


@dataclass(frozen=True)
class SttResult:
    """转写结果；``fallback=True`` 表示未使用用户配置的主 provider。"""

    text: str
    provider: str
    fallback: bool = False
    requested_provider: str | None = None


async def transcribe_with_handler(
    pcm_b64: str,
    *,
    sample_rate: int,
    creds: SttCredentials,
    fallback_local: bool = True,
) -> SttResult:
    """按 ``creds.provider`` 转写；coming_soon / 未知供应商回退本地。"""
    if not pcm_b64:
        return SttResult(text="", provider="local")

    requested = (creds.provider or "local").strip()
    provider_id = requested
    meta = find_provider("recognize", provider_id)
    forced_fallback = False
    if meta and meta.get("status") == "coming_soon":
        logger.info("识别处理者 %s 尚未接通，回退本地 Whisper", provider_id)
        provider_id = "local"
        forced_fallback = True

    if meta and meta.get("recognize_via") == "native_audio" and meta.get("status") != "ready":
        logger.info("native_audio 识别未接通，回退 local")
        provider_id = "local"
        forced_fallback = True

    impl = _PROVIDERS.get(provider_id)
    # 自定义供应商没有固定 handler id；OpenAI Chat 格式的音频模型统一走
    # input_audio 适配器（MiMo ASR 就是该协议）。
    if impl is None and creds.protocol == "openai_chat":
        impl = _PROVIDERS["mimo_audio"]
        provider_id = requested
    if impl is None:
        logger.warning("未知识别处理者 %s，回退 local", provider_id)
        impl = _PROVIDERS["local"]
        provider_id = "local"
        forced_fallback = True

    text = ""
    try:
        text = await impl.transcribe(pcm_b64, sample_rate=sample_rate, creds=creds)
    except Exception as e:
        logger.error("ASR provider=%s 异常: %s", provider_id, e)

    if text:
        return SttResult(
            text=text,
            provider=provider_id,
            fallback=forced_fallback or provider_id != requested,
            requested_provider=requested,
        )

    fallback_handler = (creds.fallback_handler or "local").strip()
    if creds.fallback_mode in ("none", "text_only"):
        return SttResult(
            text="",
            provider=provider_id,
            fallback=True,
            requested_provider=requested,
        )
    if (
        fallback_local
        and fallback_handler not in ("", "none", "text_only")
        and fallback_handler != requested
    ):
        fallback_impl = _PROVIDERS.get(fallback_handler)
        if fallback_impl is not None:
            logger.info("ASR provider=%s 无结果，回退 %s", provider_id, fallback_handler)
            fallback_creds = replace(
                creds,
                provider=fallback_handler,
                protocol="openai_chat" if fallback_handler == "local" else creds.protocol,
                model="base" if fallback_handler == "local" else creds.model,
            )
            try:
                fallback_text = await fallback_impl.transcribe(
                    pcm_b64,
                    sample_rate=sample_rate,
                    creds=fallback_creds,
                )
            except Exception as fe:
                # 主供应商已失败，降级路径异常也不向上抛（与主路径容错语义一致）
                logger.error("ASR fallback provider=%s 异常: %s", fallback_handler, fe)
                fallback_text = ""
            return SttResult(
                text=fallback_text,
                provider=fallback_handler,
                fallback=True,
                requested_provider=requested,
            )
    if fallback_local and fallback_handler not in ("", "none", "text_only") and provider_id != "local":
        logger.info("ASR provider=%s 配置的降级处理者 %s 不可用", provider_id, fallback_handler)
        return SttResult(
            text="",
            provider=provider_id,
            fallback=True,
            requested_provider=requested,
        )
    return SttResult(
        text="",
        provider=provider_id,
        fallback=forced_fallback,
        requested_provider=requested,
    )

"""TTS 统一入口：支持 Edge / MiniMax / OpenAI 兼容（含 Mimo）/ 仅字幕。"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

from shared.config import get_settings
from shared.core.security import make_pinned_async_client
from shared.capabilities.voice.tts.edge import synthesize_to_base64 as edge_synthesize
from shared.capabilities.voice.tts.edge import DEFAULT_VOICE as EDGE_DEFAULT_VOICE
from shared.capabilities.voice.tts.minimax import (
    DEFAULT_BASE as MINIMAX_DEFAULT_BASE,
    DEFAULT_MODEL as MINIMAX_DEFAULT_MODEL,
    DEFAULT_VOICE as MINIMAX_DEFAULT_VOICE,
    synthesize_minimax_to_base64,
)
from shared.capabilities.voice.config.catalog import find_provider

logger = logging.getLogger(__name__)


@dataclass
class TtsCredentials:
    handler: str = "edge"
    mode: str = "tts_from_text"  # tts_from_text | native_audio | text_only
    protocol: str = "openai_chat"
    api_base: str = ""
    api_key: str = ""
    model: str = ""
    voice: str = "zh-CN-XiaoxiaoNeural"
    fallback_handler: str = "edge"
    fallback_mode: str = "tts_from_text"


async def synthesize_speech(
    text: str,
    *,
    creds: TtsCredentials,
    rate: str = "+0%",
    pitch: str = "+0Hz",
) -> str:
    """合成语音 base64；text_only / coming_soon / 失败时返回空串（上层继续字幕）。"""
    handler = (creds.handler or "edge").strip()
    mode = (creds.mode or "tts_from_text").strip()

    if mode == "text_only" or handler == "none":
        return ""

    meta = find_provider("speak", handler)
    if meta and meta.get("status") == "coming_soon":
        logger.info("播报处理者 %s 尚未接通，执行配置的降级处理", handler)
        return await _synthesize_fallback(text, creds, rate=rate, pitch=pitch)

    if mode == "native_audio":
        logger.info("native_audio 播报未接通，执行配置的降级处理")
        return await _synthesize_fallback(text, creds, rate=rate, pitch=pitch)

    try:
        audio = await _synthesize_handler(text, creds, handler, rate=rate, pitch=pitch)
    except Exception as e:
        logger.error("播报处理者 %s 异常: %s", handler, e)
        audio = ""
    if audio:
        return audio
    logger.info("播报处理者 %s 失败，执行配置的降级处理", handler)
    return await _synthesize_fallback(text, creds, rate=rate, pitch=pitch)


async def _synthesize_handler(
    text: str,
    creds: TtsCredentials,
    handler: str,
    *,
    rate: str,
    pitch: str,
) -> str:
    if handler == "none":
        return ""
    if handler == "edge":
        try:
            return await edge_synthesize(
                text, creds.voice or "zh-CN-XiaoxiaoNeural", rate=rate, pitch=pitch
            )
        except Exception as e:
            logger.error("Edge TTS 失败: %s", e)
            return ""
    if handler == "minimax_speech":
        return await synthesize_minimax_to_base64(
            text,
            api_key=creds.api_key,
            api_base=creds.api_base or MINIMAX_DEFAULT_BASE,
            model=creds.model or MINIMAX_DEFAULT_MODEL,
            voice=creds.voice or MINIMAX_DEFAULT_VOICE,
        )
    return await _synthesize_openai_compat(text, creds)


async def _synthesize_fallback(
    text: str,
    creds: TtsCredentials,
    *,
    rate: str,
    pitch: str,
) -> str:
    fallback = (creds.fallback_handler or "edge").strip()
    if (
        not fallback
        or fallback in ("none", "text_only")
        or creds.fallback_mode == "text_only"
        or fallback == (creds.handler or "").strip()
    ):
        return ""
    fallback_creds = TtsCredentials(
        handler=fallback,
        mode=creds.fallback_mode or "tts_from_text",
        protocol=creds.protocol,
        api_base=creds.api_base,
        api_key=creds.api_key,
        model=creds.model,
        voice=(EDGE_DEFAULT_VOICE if fallback == "edge" else creds.voice),
        fallback_handler="none",
        fallback_mode="text_only",
    )
    return await _synthesize_handler(
        text, fallback_creds, fallback, rate=rate, pitch=pitch
    )


async def _synthesize_openai_compat(text: str, creds: TtsCredentials) -> str:
    if creds.protocol != "openai_chat":
        logger.warning("自定义 TTS 暂不支持 API 格式 %s", creds.protocol)
        return ""
    api_key = (creds.api_key or "").strip()
    api_base = (creds.api_base or "").rstrip("/")
    model = creds.model or "mimo-v2.5-tts"
    voice = creds.voice or "mimo_default"
    if not api_key or not api_base:
        return ""

    url = f"{api_base}/chat/completions"
    payload = {
        "model": model,
        "messages": [
            {"role": "user", "content": "用自然的中文女声，正常语速，平稳地播报。"},
            {"role": "assistant", "content": text},
        ],
        "audio": {"format": "wav", "voice": voice},
    }
    headers = {"api-key": api_key, "Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    settings = get_settings()
    try:
        async with make_pinned_async_client(
            api_base,
            allow_local=settings.allow_local_llm,
            require_https=bool(settings.is_prod),
            timeout=120.0,
        ) as client:
            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPStatusError as e:
        logger.error("OpenAI 兼容 TTS HTTP %s: %s", e.response.status_code, e.response.text[:200])
        return ""
    except Exception as e:
        logger.error("OpenAI 兼容 TTS 失败: %s", e)
        return ""

    msg = data.get("choices", [{}])[0].get("message", {}) if data.get("choices") else {}
    audio = msg.get("audio")
    if isinstance(audio, dict) and audio.get("data"):
        return audio["data"]
    return ""


async def synthesize_custom_speech(text: str, *, creds: TtsCredentials) -> str:
    """只测试自定义主处理器，不自动执行 Edge 降级。"""
    return await _synthesize_openai_compat(text, creds)


async def synthesize_primary_speech(
    text: str,
    *,
    creds: TtsCredentials,
    rate: str = "+0%",
    pitch: str = "+0Hz",
) -> str:
    """只执行主播报处理器，不触发降级，用于设置页连通性测试。"""
    handler = (creds.handler or "edge").strip()
    mode = (creds.mode or "tts_from_text").strip()
    if mode == "text_only" or handler == "none":
        return ""
    meta = find_provider("speak", handler)
    if meta and meta.get("status") == "coming_soon":
        return ""
    if mode == "native_audio":
        return ""
    try:
        return await _synthesize_handler(text, creds, handler, rate=rate, pitch=pitch)
    except Exception as e:
        logger.error("主播报处理器 %s 测试失败: %s", handler, e)
        return ""

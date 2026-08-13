"""MiniMax Speech TTS（文本 → 音频）。"""

from __future__ import annotations

import base64
import logging

import httpx

from shared.config import get_settings
from shared.core.security import make_pinned_async_client

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "speech-2.8-hd"
DEFAULT_VOICE = "male-qn-qingse"
DEFAULT_BASE = "https://api.minimaxi.com/v1"


async def synthesize_minimax_to_base64(
    text: str,
    *,
    api_key: str,
    api_base: str = DEFAULT_BASE,
    model: str = DEFAULT_MODEL,
    voice: str = DEFAULT_VOICE,
) -> str:
    """调用 MiniMax t2a_v2；成功返回 mp3/wav base64，失败返回空串。"""
    key = (api_key or "").strip()
    base = (api_base or DEFAULT_BASE).rstrip("/")
    clean = (text or "").strip()
    if not key or not clean:
        return ""

    # MiniMax 文档：POST /v1/t2a_v2
    url = f"{base}/t2a_v2"
    body = {
        "model": model or DEFAULT_MODEL,
        "text": clean,
        "stream": False,
        "voice_setting": {
            "voice_id": voice or DEFAULT_VOICE,
            "speed": 1.0,
            "vol": 1.0,
            "pitch": 0,
        },
        "audio_setting": {
            "sample_rate": 32000,
            "bitrate": 128000,
            "format": "mp3",
            "channel": 1,
        },
    }
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    settings = get_settings()
    try:
        async with make_pinned_async_client(
            url,
            allow_local=settings.allow_local_llm,
            require_https=bool(settings.is_prod),
            timeout=60.0,
        ) as client:
            resp = await client.post(url, headers=headers, json=body)
            resp.raise_for_status()
            payload = resp.json()
    except httpx.HTTPStatusError as e:
        body_txt = ""
        try:
            body_txt = (e.response.text or "")[:200]
        except Exception:
            pass
        logger.error("MiniMax TTS HTTP %s: %s", e.response.status_code, body_txt)
        return ""
    except Exception as e:
        logger.error("MiniMax TTS 失败: %s", e)
        return ""

    data = payload.get("data") or {}
    audio = data.get("audio") or payload.get("audio") or ""
    if isinstance(audio, str) and audio:
        # 已是 hex 或 base64；MiniMax 常返回 hex
        try:
            raw = bytes.fromhex(audio)
            return base64.b64encode(raw).decode("ascii")
        except ValueError:
            return audio
    logger.warning("MiniMax TTS 响应无 audio 字段 keys=%s", list(payload.keys())[:8])
    return ""

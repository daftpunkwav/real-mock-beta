"""OpenAI 兼容 / Mimo 音频转写适配器（走 chat.completions 以支持 mimo-v2.5-asr）。"""

from __future__ import annotations

import base64
import logging

import httpx

from shared.config import get_settings
from shared.core.security import make_pinned_async_client, redact_api_key
from shared.capabilities.voice.stt.base import SttCredentials

logger = logging.getLogger(__name__)


class MimoAudioProvider:
    """调用 OpenAI Chat，把音频作为 input_audio 传给 ASR 模型。"""

    async def transcribe(
        self, pcm_b64: str, *, sample_rate: int, creds: SttCredentials
    ) -> str:
        api_key = (creds.api_key or "").strip()
        api_base = (creds.api_base or "").rstrip("/")
        model = creds.model or "mimo-v2.5-asr"
        if not api_key or not api_base:
            return ""

        # router 传入的是 wav（或 pcm）的 base64；优先视为带 RIFF 头的 wav
        wav_bytes = _decode_audio(pcm_b64)
        if not wav_bytes:
            return ""
        audio_b64 = base64.b64encode(wav_bytes).decode("ascii")
        data_uri = f"data:audio/wav;base64,{audio_b64}"

        url = f"{api_base}/chat/completions"
        payload = {
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "input_audio", "input_audio": {"data": data_uri}}
                    ],
                }
            ],
            "asr_options": {"language": "zh"},
        }
        headers = {"api-key": api_key, "Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

        settings = get_settings()
        try:
            async with make_pinned_async_client(
                api_base,
                allow_local=settings.allow_local_llm,
                require_https=bool(settings.is_prod),
                timeout=60.0,
            ) as client:
                resp = await client.post(url, headers=headers, json=payload)
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPStatusError as e:
            logger.error(
                "MimoAudio ASR HTTP %s key=%s: %s",
                e.response.status_code,
                redact_api_key(api_key),
                e.response.text[:200],
            )
            return ""
        except Exception as e:
            logger.error("MimoAudio ASR 失败 key=%s: %s", redact_api_key(api_key), e)
            return ""

        msg = data.get("choices", [{}])[0].get("message", {}) if data.get("choices") else {}
        text = ""
        content = msg.get("content")
        if isinstance(content, str):
            text = content
        elif isinstance(content, list):
            text = "".join(p.get("text", "") for p in content if isinstance(p, dict))
        return text.strip()


def _decode_audio(pcm_b64: str) -> bytes:
    try:
        raw = base64.b64decode(pcm_b64)
        if raw[:4] == b"RIFF":
            return raw
        from shared.capabilities.voice.stt.cloud import pcm_base64_to_wav_bytes

        return pcm_base64_to_wav_bytes(pcm_b64, 16000)
    except Exception:
        return b""


async def transcribe_pcm_cloud(
    pcm_b64: str,
    *,
    sample_rate: int = 16000,
    model: str = "whisper-1",
    api_base: str = "",
    api_key: str = "",
) -> str:
    """OpenAI 兼容 /audio/transcriptions 转写（与 tests 兼容的旧函数）。"""
    from shared.capabilities.voice.stt.cloud import transcribe_pcm_cloud as _cloud

    return await _cloud(
        pcm_b64,
        sample_rate=sample_rate,
        model=model,
        api_base=api_base,
        api_key=api_key,
    )


class OpenAICompatProvider:
    async def transcribe(
        self, pcm_b64: str, *, sample_rate: int, creds: SttCredentials
    ) -> str:
        return await transcribe_pcm_cloud(
            pcm_b64,
            sample_rate=sample_rate,
            model=creds.model or "FunAudioLLM/SenseVoiceSmall",
            api_base=creds.api_base,
            api_key=creds.api_key,
        )

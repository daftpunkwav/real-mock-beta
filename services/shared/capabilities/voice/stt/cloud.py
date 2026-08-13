"""OpenAI 兼容云端语音转写（/v1/audio/transcriptions）。

使用**独立 ASR 凭证**对接 OpenAI、Groq、SiliconFlow 等；
禁止静默复用面试思考 LLM（如 MiniMax Coding Plan）的 Key。
"""

from __future__ import annotations

import logging

import httpx

from shared.config import get_settings
from shared.core.security import make_pinned_async_client, redact_api_key
from shared.capabilities.voice.stt.whisper import pcm_base64_to_wav_bytes

logger = logging.getLogger(__name__)

# 技术面试中英混说提示，帮助保留专有名词
_BILINGUAL_PROMPT = (
    "以下是中英文技术面试对话。可能包含：面试官、候选人、自我介绍、"
    "API、Python、JavaScript、React、Agent、GitHub、Docker、Kubernetes、"
    "SQL、HTTP、REST、字节跳动、算法、项目经验等词汇。"
)

# 本地 faster-whisper 尺寸名；其余视为云端模型 id
LOCAL_WHISPER_SIZES = frozenset(
    {
        "tiny",
        "base",
        "small",
        "medium",
        "large",
        "large-v1",
        "large-v2",
        "large-v3",
        "distil-large-v3",
        "distil-small.en",
    }
)


def is_local_stt_model(model: str) -> bool:
    return (model or "").strip().lower() in LOCAL_WHISPER_SIZES


def resolve_cloud_stt_model(model: str) -> str:
    """本地尺寸名时回退到通用云端模型 whisper-1。"""
    m = (model or "").strip()
    if not m or is_local_stt_model(m):
        return "whisper-1"
    return m


async def transcribe_pcm_cloud(
    pcm_b64: str,
    *,
    sample_rate: int = 16000,
    model: str = "whisper-1",
    api_base: str = "",
    api_key: str = "",
    language: str | None = None,
) -> str:
    """调用 OpenAI 兼容 transcriptions；失败返回空串。"""
    key = (api_key or "").strip()
    base = (api_base or "").rstrip("/")
    if not key or not base:
        return ""

    raw_len = 0
    try:
        import base64

        raw_len = len(base64.b64decode(pcm_b64))
    except Exception:
        return ""
    # < ~0.35s int16 mono
    if raw_len < sample_rate * 2 * 0.35:
        return ""

    try:
        wav_bytes = pcm_base64_to_wav_bytes(pcm_b64, sample_rate)
    except Exception as e:
        logger.warning("PCM→WAV 失败: %s", e)
        return ""

    url = f"{base}/audio/transcriptions"
    cloud_model = resolve_cloud_stt_model(model)
    settings = get_settings()
    data: dict[str, str] = {
        "model": cloud_model,
        "response_format": "json",
        "prompt": _BILINGUAL_PROMPT,
    }
    # 面试以中文为主；不强制时部分供应商自动检测更好，此处默认 zh 提升中文准确率
    if language:
        data["language"] = language
    else:
        data["language"] = "zh"

    files = {"file": ("audio.wav", wav_bytes, "audio/wav")}
    headers = {"Authorization": f"Bearer {key}"}

    try:
        async with make_pinned_async_client(
            url,
            allow_local=settings.allow_local_llm,
            require_https=bool(settings.is_prod),
            timeout=45.0,
        ) as client:
            resp = await client.post(url, headers=headers, data=data, files=files)
            resp.raise_for_status()
            payload = resp.json()
    except httpx.HTTPStatusError as e:
        body = ""
        try:
            body = (e.response.text or "")[:200]
        except Exception:
            pass
        logger.error(
            "云端 STT HTTP %s key=%s: %s",
            e.response.status_code,
            redact_api_key(key),
            body,
        )
        return ""
    except Exception as e:
        logger.error("云端 STT 失败 key=%s: %s", redact_api_key(key), e)
        return ""

    text = ""
    if isinstance(payload, dict):
        text = str(payload.get("text") or "").strip()
    elif isinstance(payload, str):
        text = payload.strip()
    if len(text) < 2:
        return ""
    return text

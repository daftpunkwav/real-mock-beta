"""Edge TTS 语音合成。

edge-tts 客户端会转义正文并自行包装 SSML，因此不支持注入 express-as；
情绪拟真通过 rate/pitch 实现，失败时降级为默认韵律纯文本。
"""

from __future__ import annotations

import base64
import logging
import re

logger = logging.getLogger(__name__)

# 预设中文音色
VOICE_PRESETS = {
    "xiaoxiao": "zh-CN-XiaoxiaoNeural",
    "yunxi": "zh-CN-YunxiNeural",
    "yunyang": "zh-CN-YunyangNeural",
    "xiaoyi": "zh-CN-XiaoyiNeural",
    "yunjian": "zh-CN-YunjianNeural",
}

DEFAULT_VOICE = VOICE_PRESETS["xiaoxiao"]

# 句末硬切分点（与流式入队策略对齐）
_HARD_END = frozenset("。！？!?；;…\n")
# 长句软切分（字数达标后）
_SOFT_BREAK = frozenset("，、,")
# 软切字数在短/中/长之间轮转，避免句句等长、不真实
_SOFT_MIN_ROTATION = (10, 14, 18, 24, 32)
_SOFT_MIN_CHARS = 18


def split_sentences(text: str) -> list[str]:
    """按中英文句号切分，用于流式 TTS。"""
    clean = _plain_text_for_tts(text)
    parts = re.split(r"(?<=[。！？!?；;…\.\n])", clean)
    return [p.strip() for p in parts if p.strip()]


def should_flush_sentence_buffer(buf: str, soft_min: int | None = None) -> bool:
    """流式缓冲是否应立刻入队合成。

    - 遇硬句末标点 → 切
    - 长度 ≥ soft_min 且遇逗号/顿号 → 软切（soft_min 由调用方轮转，模拟长短句）
    - 超长硬切：≥ 48 字无标点也切，避免单句过长
    """
    if not buf:
        return False
    last = buf[-1]
    if last in _HARD_END:
        return True
    min_chars = soft_min if soft_min is not None else _SOFT_MIN_CHARS
    if len(buf) >= min_chars and last in _SOFT_BREAK:
        return True
    if len(buf) >= 48:
        return True
    return False


def next_soft_min(index: int) -> tuple[int, int]:
    """返回 (本轮 soft_min, 下一轮 index)。"""
    mins = _SOFT_MIN_ROTATION
    i = index % len(mins)
    return mins[i], index + 1


def extract_emotion(text: str) -> str:
    m = re.search(r"\[emotion:(\w+)\]", text)
    return m.group(1) if m else "neutral"


def _plain_text_for_tts(text: str) -> str:
    """去掉控制标记与 markdown 装饰，避免 TTS 念出「星号」。"""
    clean = re.sub(r"\[(PHASE_COMPLETE|INTERVIEW_COMPLETE|emotion:\w+)\]", "", text)
    # **粗体** / *斜体* → 保留正文
    clean = re.sub(r"\*\*([^*]+)\*\*", r"\1", clean)
    clean = re.sub(r"\*([^*]+)\*", r"\1", clean)
    clean = re.sub(r"__([^_]+)__", r"\1", clean)
    clean = re.sub(r"_([^_]+)_", r"\1", clean)
    clean = re.sub(r"`+", "", clean)
    clean = re.sub(r"#{1,6}\s*", "", clean)
    clean = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", clean)
    # 残留孤立星号（含全角＊）
    clean = re.sub(r"[*＊]+", "", clean)
    clean = re.sub(r"[ \t]{2,}", " ", clean)
    return clean.strip()


async def _stream_communicate(communicate) -> bytes:
    audio_bytes = b""
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio_bytes += chunk["data"]
    return audio_bytes


async def synthesize_to_base64(
    text: str,
    voice: str | None = None,
    *,
    rate: str = "+0%",
    pitch: str = "+0Hz",
    style: str | None = None,  # noqa: ARG001 — 保留签名；edge-tts 不支持 express-as
) -> str:
    """合成语音并返回 base64 MP3。

    优先 ``Communicate(text, voice, rate=, pitch=)``；失败降级为默认韵律；
    再失败抛错。``style`` 参数保留兼容，实际由调用方映射进 rate/pitch。
    """
    del style  # edge-tts 无法注入 express-as，情绪已体现在 rate/pitch
    plain = _plain_text_for_tts(text)
    if not plain:
        return ""
    import edge_tts

    voice_id = voice or DEFAULT_VOICE
    attempts: list[tuple[str, object]] = [
        ("prosody", edge_tts.Communicate(plain, voice_id, rate=rate, pitch=pitch)),
        ("plain", edge_tts.Communicate(plain, voice_id)),
    ]

    last_err: Exception | None = None
    for label, communicate in attempts:
        try:
            audio_bytes = await _stream_communicate(communicate)
            if audio_bytes:
                if label != "prosody":
                    logger.debug(
                        "Edge TTS 降级为纯文本 voice=%s rate=%s", voice_id, rate
                    )
                return base64.b64encode(audio_bytes).decode("ascii")
        except Exception as e:
            last_err = e
            logger.info("Edge TTS 路径失败 label=%s: %s", label, e)
            continue

    if last_err:
        raise RuntimeError(f"Edge TTS 合成失败: {last_err}") from last_err
    raise RuntimeError("Edge TTS 返回空音频")


async def synthesize_to_base64_safe(
    text: str,
    voice: str | None = None,
    *,
    rate: str = "+0%",
    pitch: str = "+0Hz",
    style: str | None = None,
) -> str:
    """合成语音；失败记日志并返回空串（兼容旧调用）。"""
    try:
        return await synthesize_to_base64(
            text, voice, rate=rate, pitch=pitch, style=style
        )
    except Exception as e:
        logger.error("Edge TTS 失败: %s", e)
        return ""

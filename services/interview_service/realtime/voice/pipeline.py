"""语音管线：STT 文本选择、回采判定、短句 TTS。

句子级 TTS 队列见 :mod:`tts_queue`。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from interview_service.services.interview.agent_text import strip_markers
from shared.capabilities.voice.tts import TtsCredentials, synthesize_speech
from shared.capabilities.voice.tts.edge import (
    extract_emotion,
    _plain_text_for_tts,
)
from shared.capabilities.voice.tts.voice_resolve import VoiceProsody, with_emotion

logger = logging.getLogger(__name__)


def _latin_letter_ratio(text: str) -> float:
    """字母中拉丁字符占比，用于判断英文内容。"""
    letters = [c for c in text if c.isalpha() or "\u4e00" <= c <= "\u9fff"]
    if not letters:
        return 0.0
    latin = sum(1 for c in letters if "a" <= c.lower() <= "z")
    return latin / len(letters)


def _pick_stt_text(browser_text: str, asr_text: str) -> str:
    """合并浏览器预览与云端/本地 ASR：有 ASR 终稿时优先采信（浏览器中文常误听）。"""
    browser = (browser_text or "").strip()
    asr = (asr_text or "").strip()
    if asr and not browser:
        return asr
    if browser and not asr:
        return browser
    if not browser and not asr:
        return ""

    wr = _latin_letter_ratio(asr)
    br = _latin_letter_ratio(browser)
    # 浏览器 zh-CN 常把英文听成乱码；ASR 检出明显英文时采用 ASR
    if wr >= 0.35 and br < 0.25:
        return asr
    if wr >= 0.5:
        return asr
    # 中文/混说：默认采信第三方 ASR（浏览器仅作预览）
    if len(asr) >= 2:
        return asr
    return browser


def _should_skip_whisper(browser_text: str) -> bool:
    """已废弃：始终跑云端/本地 ASR。保留函数名以免外部引用断裂。"""
    return False


def _normalize_echo_text(text: str) -> str:
    import re

    return re.sub(r"[\s\*\#`~，。！？、,.!?;:：；\"'“”‘’\-—…（）()【】\[\]]+", "", text).lower()


def _is_echo_of_assistant(user_text: str, assistant_text: str) -> bool:
    """候选人文本是否高度像上一句面试官发言（扬声器回采）。"""
    from difflib import SequenceMatcher

    u = _normalize_echo_text(user_text or "")
    a = _normalize_echo_text(assistant_text or "")
    if len(u) < 12 or len(a) < 12:
        return False
    probe_u = u[: min(40, len(u))]
    probe_a = a[: min(40, len(a))]
    if probe_u in a or probe_a in u:
        return True
    if SequenceMatcher(None, u[:120], a[:120]).ratio() >= 0.55:
        return True
    short = u[: min(24, len(u))]
    if len(short) >= 12 and short in a:
        return True
    return False


class VoicePipelineMixin:
    """短句 TTS；依赖 ctx.tts_voice / ctx.session_prosody / ctx.tts_creds / send。"""

    if TYPE_CHECKING:
        from interview_service.realtime.core.context import ConnectionContext

    ctx: "ConnectionContext"

    async def _speak_one(self, sentence: str) -> None:
        clean = _plain_text_for_tts(strip_markers(sentence))
        if not clean:
            return
        base = self.ctx.session_prosody or VoiceProsody(voice=self.ctx.tts_voice)
        emo = extract_emotion(sentence)
        p = with_emotion(base, emo)
        try:
            tts_creds = self.ctx.tts_creds or TtsCredentials(
                handler="edge", voice=p.voice
            )
            audio_b64 = await synthesize_speech(
                clean,
                creds=TtsCredentials(
                    handler=tts_creds.handler,
                    mode=tts_creds.mode,
                    protocol=tts_creds.protocol,
                    api_base=tts_creds.api_base,
                    api_key=tts_creds.api_key,
                    model=tts_creds.model,
                    voice=p.voice or tts_creds.voice,
                    fallback_handler=tts_creds.fallback_handler,
                    fallback_mode=tts_creds.fallback_mode,
                ),
                rate=p.rate,
                pitch=p.pitch,
            )
        except Exception as e:
            logger.error("TTS 短句失败: %s", e)
            await self.send(
                "error",
                message="语音合成失败，请检查网络（文字内容仍可用）",
                code="C2002",
                retryable=True,
            )
            return
        if audio_b64:
            await self._tts_send("tts_audio", data=audio_b64, sentence=clean)
            self._mark_tts_sent()
        else:
            await self.send(
                "tts_failed",
                message="语音合成返回空音频，请检查网络或改用文字作答",
            )

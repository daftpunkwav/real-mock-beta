"""语音管线：STT 文本选择、回采判定、句子级 TTS 队列。"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from shared.config import get_settings
from interview_service.services.interview.agent import strip_markers
from shared.capabilities.voice.tts import TtsCredentials, synthesize_speech
from shared.capabilities.voice.tts.edge import (
    extract_emotion,
    _plain_text_for_tts,
)
from shared.capabilities.voice.tts.voice_resolve import VoiceProsody, with_emotion

logger = logging.getLogger(__name__)
settings = get_settings()

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


class _SentenceTTSQueue:
    """串行 TTS 队列：保证句子按到达顺序逐个合成并播放，不与 LLM 流相互阻塞。

    内存治理：队列长度超过 ``_MAX_QUEUE_SIZE`` 时丢弃最早的句子，
    防止 TTS 慢、网络抖动时内存无界增长。
    """

    # 上限：约 3-5 分钟的连续面试内容。超出时优先丢弃已入队的旧句以保证实时性。
    _MAX_QUEUE_SIZE: int = 50

    def __init__(self) -> None:
        # (text, emotion) ；None 为哨兵结束
        self._queue: asyncio.Queue[tuple[str, str] | None] = asyncio.Queue()
        self._worker_task: asyncio.Task | None = None
        self._lock = asyncio.Lock()
        self._dropped_count = 0
        self._prosody: VoiceProsody = VoiceProsody(voice=settings.tts_voice)
        self._fail_count = 0
        self._on_sent: Any = None
        # 打断世代：clear 后旧合成结果不再发出
        self._speak_gen: int = 0
        self._tts_creds: TtsCredentials = TtsCredentials(handler="edge")

    def set_voice(self, voice: str) -> None:
        """兼容旧调用：仅更新音色，保留现有 rate/pitch。"""
        if voice:
            self._prosody = VoiceProsody(
                voice=voice,
                rate=self._prosody.rate,
                pitch=self._prosody.pitch,
            )
            self._tts_creds.voice = voice

    def set_prosody(self, prosody: VoiceProsody) -> None:
        """绑定本场会话的基线音色与韵律。"""
        self._prosody = prosody
        self._tts_creds.voice = prosody.voice

    def set_tts_creds(self, creds: TtsCredentials) -> None:
        """绑定语音输出处理器凭证。"""
        self._tts_creds = creds

    def set_on_sent(self, callback) -> None:
        """每成功发出一条 tts_audio 时回调（用于等待客户端播完）。"""
        self._on_sent = callback

    async def start(self, send_callback) -> None:
        """启动后台 worker；每个 WS 连接初始化时调用一次。"""
        self._send = send_callback
        if self._worker_task is None or self._worker_task.done():
            self._worker_task = asyncio.create_task(self._worker())

    async def clear(self) -> None:
        """候选人打断：丢弃未播句子，作废在途合成。"""
        self._speak_gen += 1
        drained = 0
        while True:
            try:
                item = self._queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            if item is not None:
                drained += 1
            try:
                self._queue.task_done()
            except ValueError:
                pass
        if drained:
            logger.info("TTS 队列因打断清空 %d 句", drained)

    async def stop(self) -> None:
        """结束 worker，丢弃未播放的句子。"""
        await self.clear()
        if self._worker_task is not None and not self._worker_task.done():
            await self._queue.put(None)
            await self._worker_task
        if self._dropped_count:
            logger.info("TTS 队列丢弃 %d 句(超过上限)", self._dropped_count)

    async def enqueue(self, sentence: str, emotion: str | None = None) -> None:
        emo = (emotion or extract_emotion(sentence) or "neutral").strip().lower()
        clean = _plain_text_for_tts(strip_markers(sentence)).strip()
        if not clean:
            return
        # 队列过长时丢弃最早的旧句，避免内存膨胀
        if self._queue.qsize() >= self._MAX_QUEUE_SIZE:
            try:
                self._queue.get_nowait()
                self._queue.task_done()
                self._dropped_count += 1
            except asyncio.QueueEmpty:
                pass
        await self._queue.put((clean, emo))

    async def flush_remainder(self, sentence: str, emotion: str | None = None) -> None:
        """回合结束时把残留 buffer 入队，并等待队列全部处理完。"""
        if sentence.strip():
            await self.enqueue(sentence, emotion=emotion)
        # join：等 worker 对每个 put 调用 task_done，真正排空队列
        await self._queue.join()

    async def _worker(self) -> None:
        while True:
            item = await self._queue.get()
            try:
                if item is None:
                    return
                text, emotion = item
                gen = self._speak_gen
                p = with_emotion(self._prosody, emotion)
                async with self._lock:
                    if gen != self._speak_gen:
                        continue
                    try:
                        tts_creds = TtsCredentials(
                            handler=self._tts_creds.handler,
                            mode=self._tts_creds.mode,
                            protocol=self._tts_creds.protocol,
                            api_base=self._tts_creds.api_base,
                            api_key=self._tts_creds.api_key,
                            model=self._tts_creds.model,
                            voice=p.voice or self._tts_creds.voice,
                            fallback_handler=self._tts_creds.fallback_handler,
                            fallback_mode=self._tts_creds.fallback_mode,
                        )
                        audio_b64 = await synthesize_speech(
                            text, creds=tts_creds, rate=p.rate, pitch=p.pitch
                        )
                    except Exception as e:
                        self._fail_count += 1
                        logger.error("TTS 失败 voice=%s: %s", p.voice, e)
                        if self._fail_count <= 3:
                            try:
                                await self._send(
                                    "error",
                                    message="语音合成失败，请检查网络或稍后重试（文字面试仍可用）",
                                    code="C2002",
                                    retryable=True,
                                )
                            except Exception:
                                pass
                        continue
                    if gen != self._speak_gen:
                        continue
                    if audio_b64:
                        try:
                            await self._send("tts_audio", data=audio_b64, sentence=text)
                            if callable(self._on_sent):
                                self._on_sent()
                        except Exception as e:
                            logger.warning("TTS 发送失败: %s", e)
                    else:
                        try:
                            await self._send(
                                "tts_failed",
                                message="语音合成返回空音频，请检查网络或改用文字作答",
                            )
                        except Exception:
                            pass
            finally:
                self._queue.task_done()




class VoicePipelineMixin:
    """短句 TTS；依赖 ctx.tts_voice / ctx.session_prosody / ctx.tts_creds / send。"""

    if TYPE_CHECKING:
        from interview_service.realtime.context import ConnectionContext

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

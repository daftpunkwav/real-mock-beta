"""WebSocket 面试会话共享上下文。

将 InterviewWSHandler 中散布在各 mixin TYPE_CHECKING 声明中的宿主字段
集中为一个显式 dataclass，消除隐式耦合。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from fastapi import WebSocket

from interview_service.agents.orchestrator import InterviewOrchestrator
from interview_service.realtime.events import TurnState
from interview_service.services.interview.agent import InterviewAgent
from interview_service.services.interview.runner import InterviewRunner
from shared.capabilities.ai.llm.client import LLMClient
from shared.capabilities.voice.stt import SttCredentials
from shared.capabilities.voice.tts import TtsCredentials
from shared.capabilities.voice.tts.voice_resolve import VoiceProsody


@dataclass
class ConnectionContext:
    """WebSocket 面试会话的全部可变状态。

    由 InterviewWSHandler.__init__ 构造，传给每个 mixin。
    mixin 方法通过 self.ctx.xxx 读写，不再依赖 TYPE_CHECKING 声明。
    """

    # ── 连接 ──────────────────────────────────────
    ws: WebSocket
    session_id: int
    client_access_token: str = ""
    ws_subprotocol: str | None = None
    superseded: bool = False

    # ── 话轮状态 ──────────────────────────────────
    turn_state: TurnState = TurnState.IDLE

    # ── 业务对象（handle 中赋值）──────────────────
    orchestrator: InterviewOrchestrator = field(default_factory=InterviewOrchestrator)
    agent: InterviewAgent | None = None
    llm: LLMClient | None = None
    runner: InterviewRunner | None = None

    # ── 音频缓冲 ──────────────────────────────────
    audio_buffer: list[str] = field(default_factory=list)
    audio_buffer_bytes: int = 0

    # ── TTS ───────────────────────────────────────
    tts_voice: str = ""
    session_prosody: VoiceProsody = field(default_factory=lambda: VoiceProsody(voice=""))
    tts_creds: TtsCredentials = field(default_factory=lambda: TtsCredentials(handler="edge"))
    tts_soft_idx: int = 0

    # ── STT ───────────────────────────────────────
    stt_creds: SttCredentials = field(default_factory=lambda: SttCredentials(provider="local", model="base"))
    whisper_model: str = ""
    stt_fail_streak: int = 0

    # ── 话轮锁 ────────────────────────────────────
    turn_busy: bool = False
    busy_epoch: int = 0
    stream_epoch: int = 0
    closing: bool = False

    # ── 播放 ──────────────────────────────────────
    playback_done: asyncio.Event = field(default_factory=asyncio.Event)
    playback_generation: int = 0
    awaiting_playback_gen: int = 0
    playback_wait_timeout_sec: float = 45.0
    tts_sent_this_turn: bool = False

    # ── 打断 ──────────────────────────────────────
    candidate_interrupts: int = 0
    ai_interrupts: int = 0
    mic_opened_at: float = 0.0

    # ── 静默追问 ──────────────────────────────────
    last_nudge_at: float = 0.0
    nudge_cooldown_sec: float = 25.0
    nudge_grace_sec: float = 15.0

    # ── 提示/报告 ─────────────────────────────────
    hint_inflight: str | None = None
    report_task: asyncio.Task[Any] | None = None

    # ── 后台任务 ──────────────────────────────────
    bg_tasks: set[asyncio.Task[Any]] = field(default_factory=set)

    # ── TTS 队列（由 ws_handler 注入）─────────────
    tts_queue: Any = None  # _SentenceTTSQueue，避免循环 import

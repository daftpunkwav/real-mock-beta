"""WS 连接鉴权与业务装配（mixin）：令牌校验、状态检查、管道绑定、开场/续接。"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

from shared.config import get_settings
from shared.core.constants import SessionStatus
from shared.core.session_auth import tokens_match
from interview_service.ai import session_llm, session_stt_credentials, session_tts_credentials
from interview_service.models import InterviewSession, LLMSettings
from interview_service.realtime.events import TurnState
from interview_service.realtime.session_registry import claim_session_connection
from interview_service.services.interview.session_state import InterviewSessionState
from interview_service.services.interview.runner import InterviewRunner
from shared.capabilities.voice.stt import warmup_whisper
from shared.capabilities.voice.stt.cloud import is_local_stt_model
from shared.capabilities.voice.tts.voice_resolve import VoiceProsody, resolve_prosody
from shared.capabilities.voice.config.catalog import find_provider

if TYPE_CHECKING:
    from interview_service.realtime.context import ConnectionContext

logger = logging.getLogger(__name__)
settings = get_settings()


class ConnectionAuthMixin:
    """鉴权 / 会话绑定 / 管道装配；依赖 ctx 字段与 send / set_turn / _spawn。"""

    ctx: "ConnectionContext"

    # ------------------------------------------------------------------
    # 鉴权与会话检查
    # ------------------------------------------------------------------

    async def authenticate(
        self, db: Session
    ) -> InterviewSession | None:
        """校验会话存在、访问令牌与状态；通过后占用单连接租约。

        Returns:
            校验通过的 session；失败时已发送 error 并关闭，返回 None。
        """
        session = db.query(InterviewSession).filter(
            InterviewSession.id == self.ctx.session_id
        ).first()
        if not session:
            await self._fail_and_close("面试会话不存在")
            return None
        if not tokens_match(
            getattr(session, "access_token", None), self.ctx.client_access_token
        ):
            await self._fail_and_close("无权访问该面试会话")
            return None
        if session.status not in (SessionStatus.PENDING.value, SessionStatus.ACTIVE.value):
            await self._fail_and_close("面试已结束")
            return None
        await claim_session_connection(self)
        return session

    # ------------------------------------------------------------------
    # LLM / RAG / 语音管道装配
    # ------------------------------------------------------------------

    async def bind_pipeline(
        self, db: Session, session: InterviewSession
    ) -> bool:
        """装配 LLM、Agent、Runner、STT/TTS 凭证与音色。

        Returns:
            True 表示装配完成；失败时已发送 error 并关闭，返回 False。
        """
        self.ctx.llm = session_llm(db, session)
        if not self.ctx.llm.api_key:
            await self._fail_and_close("请先配置面试思考处理器的 API Key")
            return False
        self.ctx.agent = InterviewSessionState(session, self.ctx.llm)

        rag = None
        try:
            from interview_service.capabilities.rag.company_rag import CompanyKnowledgeRAG

            rag = CompanyKnowledgeRAG(self.ctx.llm)
        except Exception as e:
            logger.warning("RAG 实例化失败，继续无 RAG 模式: %s", e)

        self.ctx.runner = InterviewRunner(session, self.ctx.llm, self.ctx.agent, rag=rag)

        row = db.query(LLMSettings).filter(LLMSettings.id == 1).first()
        # 必须先从 DB/stage 构建凭证，再取音色；否则会用 dataclass 默认值覆盖用户配置
        self.ctx.stt_creds = session_stt_credentials(db, session, row=row)
        self.ctx.tts_creds = session_tts_credentials(db, session, row=row)
        settings_voice = self.ctx.tts_creds.voice or settings.tts_voice
        if row:
            self.ctx.tts_voice = settings_voice
            asr_model = self.ctx.stt_creds.model or getattr(row, "asr_model", None) or row.stt_model
            self.ctx.whisper_model = asr_model or settings.whisper_model
            await self._announce_fallbacks()
        else:
            self.ctx.whisper_model = settings.whisper_model

        await self._bind_prosody()
        await self._warmup_stt()
        return True

    async def _announce_fallbacks(self) -> None:
        """识别/播报处理者未接通运行时（coming_soon）时提示回退。"""
        rec_meta = find_provider("recognize", self.ctx.stt_creds.provider)
        if rec_meta and rec_meta.get("status") == "coming_soon":
            await self.send(
                "info",
                message=(
                    f"识别处理者「{rec_meta.get('label')}」尚未接通运行时，"
                    "已回退本地 Whisper 转写"
                ),
            )
        speak_meta = find_provider("speak", self.ctx.tts_creds.handler)
        if speak_meta and speak_meta.get("status") == "coming_soon":
            await self.send(
                "info",
                message=(
                    f"播报处理者「{speak_meta.get('label')}」尚未接通运行时，"
                    "已回退 Edge TTS"
                ),
            )
        if self.ctx.tts_creds.mode == "text_only" or self.ctx.tts_creds.handler == "none":
            await self.send("info", message="已启用仅字幕模式，不播报语音")

    async def _bind_prosody(self) -> None:
        """按会话人设/头像解析音色并绑定 TTS 队列。"""
        self.ctx.session_prosody = resolve_prosody(
            avatar_id=getattr(self.ctx.agent.session, "avatar_id", None),
            personality=getattr(self.ctx.agent.session, "personality", None),
            strictness=getattr(self.ctx.agent.session, "strictness", None),
            emotion=None,
            llm_settings_voice=self.ctx.tts_creds.voice or self.ctx.tts_voice,
        )
        if self.ctx.tts_creds.handler not in ("edge", "minimax_speech", "none"):
            self.ctx.session_prosody = VoiceProsody(
                voice=self.ctx.tts_creds.voice or self.ctx.tts_voice or "mimo_default",
                rate=self.ctx.session_prosody.rate,
                pitch=self.ctx.session_prosody.pitch,
            )
        self.ctx.tts_voice = self.ctx.session_prosody.voice
        self.ctx.tts_creds.voice = self.ctx.tts_voice
        self.ctx.tts_queue.set_prosody(self.ctx.session_prosody)
        self.ctx.tts_queue.set_tts_creds(self.ctx.tts_creds)
        self.ctx.tts_queue.set_on_sent(self._mark_tts_sent)
        logger.info(
            "管道绑定 sid=%s asr=%s speak=%s voice=%s rate=%s pitch=%s",
            self.ctx.session_id,
            self.ctx.stt_creds.provider,
            self.ctx.tts_creds.handler,
            self.ctx.session_prosody.voice,
            self.ctx.session_prosody.rate,
            self.ctx.session_prosody.pitch,
        )

    async def _warmup_stt(self) -> None:
        """预载 Whisper 模型（本地/云端均预热 base 兜底）。"""
        if self.ctx.stt_creds.provider == "local" or is_local_stt_model(self.ctx.whisper_model):
            local_m = self.ctx.whisper_model if is_local_stt_model(self.ctx.whisper_model) else "base"
            self._spawn(warmup_whisper(local_m))
        else:
            self._spawn(warmup_whisper("base"))

    # ------------------------------------------------------------------
    # 连接建立后推进（开场 / 续接）
    # ------------------------------------------------------------------

    async def start_session_flow(self, session: InterviewSession, db: Session) -> None:
        """PENDING 开场白；ACTIVE 等待候选人继续。"""
        if session.status == SessionStatus.PENDING.value:
            await self.ctx.tts_queue.start(self._tts_send)
            await self.set_turn(TurnState.AI_SPEAKING)
            await self._stream_events_with_tts(
                self._consume_runner_opening(db),
                db=db,
                session=session,
                auto_hint=True,
            )
            await self._open_mic_after_playback()
        elif session.status == SessionStatus.ACTIVE.value:
            await self.ctx.tts_queue.start(self._tts_send)
            self._begin_playback_wait()
            self.ctx.tts_sent_this_turn = False
            await self.set_turn(TurnState.USER_SPEAKING)


__all__ = ["ConnectionAuthMixin"]

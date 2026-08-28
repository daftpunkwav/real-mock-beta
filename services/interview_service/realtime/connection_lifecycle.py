"""连接生命周期（WS mixin）：握手、心跳、分发。"""

from __future__ import annotations

import asyncio
import base64
import logging
import uuid
from typing import TYPE_CHECKING, Any

from fastapi import WebSocketDisconnect
from sqlalchemy.orm import Session

from interview_service.agents.vision.agent import VisionAgent
from shared.config import get_settings
from shared.core.constants import DEFAULT_LLM_RATE_LIMIT_PER_MINUTE, MAX_USER_TEXT_CHARS, SessionStatus
from shared.core.logging import set_trace_id
from shared.core.ratelimit import try_rate_limit_by_id
from shared.core.session_auth import tokens_match
from shared.database import SessionLocal
from interview_service.models import InterviewSession, LLMSettings
from interview_service.realtime.events import TurnState
from interview_service.realtime.session_registry import (
    claim_session_connection,
    release_session_connection,
)
from interview_service.services.interview.agent import InterviewAgent
from interview_service.services.interview.runner import InterviewRunner
from shared.capabilities.ai.llm.client import LLMClient
from shared.capabilities.voice.stt import warmup_whisper
from shared.capabilities.voice.stt.cloud import is_local_stt_model
from shared.capabilities.voice.tts.voice_resolve import VoiceProsody, resolve_prosody
from shared.capabilities.voice.config.catalog import find_provider
from shared.capabilities.voice.config.credentials import build_stt_credentials, build_tts_credentials

if TYPE_CHECKING:
    from interview_service.realtime.context import ConnectionContext

logger = logging.getLogger(__name__)
settings = get_settings()
_HEARTBEAT_TIMEOUT_SEC: float = 30.0
_HEARTBEAT_MAX_MISSES: int = 3
_AUDIO_BUFFER_MAX_BYTES: int = 5 * 1024 * 1024
_WS_LLM_RATE_LIMIT = DEFAULT_LLM_RATE_LIMIT_PER_MINUTE


class ConnectionLifecycleMixin:
    """握手 / 心跳 / 消息分发。"""

    ctx: "ConnectionContext"

    async def send(self, msg_type: str, **payload: Any) -> None:
        await self.ctx.ws.send_json({"type": msg_type, **payload})

    async def _tts_send(self, msg_type: str, **payload: Any) -> None:
        """TTS 通道发送：附带 playback_generation 供客户端回传。"""
        if msg_type == "tts_audio":
            payload.setdefault("playback_generation", self.ctx.awaiting_playback_gen)
        await self.send(msg_type, **payload)

    async def set_turn(self, state: TurnState) -> None:
        self.ctx.turn_state = state
        if state == TurnState.USER_SPEAKING:
            self.ctx.mic_opened_at = asyncio.get_event_loop().time()
        await self.send("turn_state", state=state.value)

    async def _fail_and_close(
        self,
        message: str,
        code: int = 4401,
        *,
        error_code: str = "B2001",
        retryable: bool = False,
    ) -> None:
        try:
            await self.send(
                "error",
                message=message,
                code=error_code,
                retryable=retryable,
            )
        except Exception:
            pass
        try:
            await self.ctx.ws.close(code=code)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # 主循环
    # ------------------------------------------------------------------

    async def handle(self) -> None:
        accept_kwargs: dict[str, str] = {}
        if self.ctx.ws_subprotocol:
            accept_kwargs["subprotocol"] = self.ctx.ws_subprotocol
        await self.ctx.ws.accept(**accept_kwargs)
        ws_tid = f"ws-{self.ctx.session_id}-{uuid.uuid4().hex[:8]}"
        set_trace_id(ws_tid)
        db = SessionLocal()
        try:
            session = db.query(InterviewSession).filter(
                InterviewSession.id == self.ctx.session_id
            ).first()
            if not session:
                await self._fail_and_close("面试会话不存在")
                return
            if not tokens_match(
                getattr(session, "access_token", None), self.ctx.client_access_token
            ):
                await self._fail_and_close("无权访问该面试会话")
                return
            if session.status not in (SessionStatus.PENDING.value, SessionStatus.ACTIVE.value):
                await self._fail_and_close("面试已结束")
                return
            await claim_session_connection(self)

            self.ctx.llm = LLMClient.from_db(db)
            if not self.ctx.llm.api_key:
                await self._fail_and_close("请先配置面试思考处理器的 API Key")
                return
            self.ctx.agent = InterviewAgent(session, self.ctx.llm)

            rag = None
            try:
                from interview_service.capabilities.rag.company_rag import CompanyKnowledgeRAG

                rag = CompanyKnowledgeRAG(self.ctx.llm)
            except Exception as e:
                logger.warning("RAG 实例化失败，继续无 RAG 模式: %s", e)

            self.ctx.runner = InterviewRunner(session, self.ctx.llm, self.ctx.agent, rag=rag)

            row = db.query(LLMSettings).filter(LLMSettings.id == 1).first()
            # 必须先从 DB/stage 构建凭证，再取音色；否则会用 dataclass 默认值覆盖用户配置
            self.ctx.stt_creds = build_stt_credentials(row, db=db)
            self.ctx.tts_creds = build_tts_credentials(row, db=db)
            settings_voice = self.ctx.tts_creds.voice or settings.tts_voice
            if row:
                self.ctx.tts_voice = settings_voice
                asr_model = self.ctx.stt_creds.model or getattr(row, "asr_model", None) or row.stt_model
                self.ctx.whisper_model = asr_model or settings.whisper_model
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
            else:
                self.ctx.whisper_model = settings.whisper_model

            self.ctx.session_prosody = resolve_prosody(
                avatar_id=getattr(session, "avatar_id", None),
                personality=getattr(session, "personality", None),
                strictness=getattr(session, "strictness", None),
                emotion=None,
                llm_settings_voice=settings_voice or self.ctx.tts_voice,
            )
            if self.ctx.tts_creds.handler not in ("edge", "minimax_speech", "none"):
                self.ctx.session_prosody = VoiceProsody(
                    voice=self.ctx.tts_creds.voice or settings_voice or "mimo_default",
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
            if self.ctx.stt_creds.provider == "local" or is_local_stt_model(self.ctx.whisper_model):
                local_m = self.ctx.whisper_model if is_local_stt_model(self.ctx.whisper_model) else "base"
                self._spawn(warmup_whisper(local_m))
            else:
                self._spawn(warmup_whisper("base"))

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

            miss_count = 0
            while not self.ctx.superseded:
                try:
                    data = await asyncio.wait_for(
                        self.ctx.ws.receive_json(),
                        timeout=_HEARTBEAT_TIMEOUT_SEC,
                    )
                except asyncio.TimeoutError:
                    if self.ctx.superseded:
                        break
                    miss_count += 1
                    if miss_count >= _HEARTBEAT_MAX_MISSES:
                        logger.warning(
                            "WS 心跳超时断开 session=%s miss=%s",
                            self.ctx.session_id, miss_count,
                        )
                        await self.send(
                            "error",
                            message="心跳超时，连接已断开",
                            code="B2002",
                            retryable=True,
                        )
                        break
                    try:
                        await self.send("server_ping", t=int(asyncio.get_event_loop().time() * 1000))
                    except Exception:
                        break
                    continue
                if self.ctx.superseded:
                    break
                miss_count = 0
                await self._dispatch(data, db, session)
        except WebSocketDisconnect:
            logger.info("WS 断开 session=%s", self.ctx.session_id)
        except Exception as e:
            logger.exception("WS 错误: %s", e)
            try:
                await self.set_turn(TurnState.USER_SPEAKING)
                await self.send(
                    "error",
                    message="服务端异常，已恢复 USER_SPEAKING",
                    code="B2001",
                    retryable=True,
                )
            except Exception:
                pass
            try:
                db.rollback()
            except Exception:
                pass
        finally:
            await release_session_connection(self)
            try:
                await self._cancel_bg_tasks()
            except Exception:
                logger.exception("取消后台任务失败")
            try:
                await asyncio.wait_for(self.ctx.tts_queue.stop(), timeout=5.0)
            except Exception:
                logger.exception("TTS queue 关闭失败")
            try:
                db.close()
            except Exception:
                logger.exception("DB 关闭失败")

    # ------------------------------------------------------------------
    # 消息分发
    # ------------------------------------------------------------------

    async def _dispatch(self, data: dict[str, Any], db: Session, session: InterviewSession) -> None:
        msg_type = data.get("type", "")
        if msg_type == "audio_chunk":
            chunk = data.get("data", "")
            if chunk:
                try:
                    new_bytes = len(base64.b64decode(chunk, validate=False))
                except Exception:
                    new_bytes = 0
                if self.ctx.audio_buffer_bytes + new_bytes > _AUDIO_BUFFER_MAX_BYTES:
                    logger.warning(
                        "audio_buffer 超上限 session=%s bytes=%s",
                        self.ctx.session_id,
                        self.ctx.audio_buffer_bytes + new_bytes,
                    )
                    await self.send(
                        "error",
                        message="音频缓存超限，请先结束当前回合",
                        code="A0004",
                    )
                    self.ctx.audio_buffer = []
                    self.ctx.audio_buffer_bytes = 0
                    return
                self.ctx.audio_buffer.append(chunk)
                self.ctx.audio_buffer_bytes += new_bytes
        elif msg_type == "stt_text":
            text = data.get("text", "").strip()
            if text:
                await self.send("stt_partial", text=text)
        elif msg_type == "pong":
            return
        elif msg_type == "vision_update":
            face = data.get("face_analysis")
            if face:
                self.ctx.orchestrator.snapshot.merge_face(face)
                self.ctx.orchestrator.snapshot.vision_summary = VisionAgent.summarize(face)
        elif msg_type == "user_turn_end":
            if not self._can_start_user_turn():
                return
            if not try_rate_limit_by_id(
                key="llm",
                client_id=f"ws-{self.ctx.session_id}",
                limit=_WS_LLM_RATE_LIMIT,
            ):
                await self.send(
                    "error",
                    message="请求过于频繁，请稍后再试",
                    code="A0002",
                    retryable=True,
                )
                return
            self._spawn(self._run_user_turn_end(data))
        elif msg_type == "silence_timeout":
            if self.ctx.turn_busy or self.ctx.closing:
                return
            self._spawn(self._on_silence_nudge())
        elif msg_type == "barge_in":
            if self.ctx.closing:
                return
            self._spawn(self._on_candidate_barge_in())
        elif msg_type == "user_text":
            text = data.get("text", "").strip()
            if len(text) > MAX_USER_TEXT_CHARS:
                await self.send(
                    "error",
                    message=f"文本过长（上限 {MAX_USER_TEXT_CHARS} 字符）",
                    code="A0003",
                )
                return
            if (
                text
                and self.ctx.turn_state == TurnState.USER_SPEAKING
                and self._can_start_user_turn()
            ):
                if not try_rate_limit_by_id(
                    key="llm",
                    client_id=f"ws-{self.ctx.session_id}",
                    limit=_WS_LLM_RATE_LIMIT,
                ):
                    await self.send(
                        "error",
                        message="请求过于频繁，请稍后再试",
                        code="A0002",
                        retryable=True,
                    )
                    return
                self._spawn(self._run_user_text(text, data))
        elif msg_type == "request_hint":
            if not try_rate_limit_by_id(
                key="llm",
                client_id=f"ws-{self.ctx.session_id}",
                limit=max(5, _WS_LLM_RATE_LIMIT // 2),
            ):
                await self.send(
                    "error",
                    message="请求过于频繁，请稍后再试",
                    code="A0002",
                    retryable=True,
                )
                return
            self._spawn(self._on_request_hint(data))
        elif msg_type == "request_finish":
            if self.ctx.closing:
                return
            self._spawn(self._on_request_finish())
        elif msg_type == "tts_playback_done":
            client_gen = data.get("generation")
            if client_gen is None or client_gen == self.ctx.awaiting_playback_gen:
                self.ctx.playback_done.set()

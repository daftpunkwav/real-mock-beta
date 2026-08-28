"""``app.realtime.ws_handler`` 单元 + 状态机测试。

覆盖：
- audio_buffer 上限保护（>5MB 强制清空 + error 事件）；
- deadlock fallback：异常路径回到 ``USER_SPEAKING``；
- SessionEvent.schema_version 默认 1；
- ``_dispatch`` 不识别的消息类型不抛错；
- pong 消息不会触发业务处理。
"""

from __future__ import annotations

import base64
from unittest.mock import AsyncMock, MagicMock

import pytest

from interview_service.realtime.events import SessionEvent, TurnState


def _make_mock_ws() -> MagicMock:
    ws = MagicMock()
    ws.accept = AsyncMock()
    ws.send_json = AsyncMock()
    ws.receive_json = AsyncMock()
    ws.close = AsyncMock()
    return ws


def _audio_b64(n_bytes: int) -> str:
    """返回 n_bytes 长度 pcm 的 base64 编码。"""
    return base64.b64encode(b"\x00" * n_bytes).decode("ascii")


class TestSessionEvent:
    def test_default_schema_version(self) -> None:
        ev = SessionEvent(type="test")
        assert ev.schema_version == 1
        assert ev.type == "test"
        assert ev.payload == {}


class TestAudioBufferCap:
    @pytest.mark.asyncio
    async def test_audio_chunk_appends(self) -> None:
        from interview_service.realtime.ws_handler import InterviewWSHandler

        ws = _make_mock_ws()
        handler = InterviewWSHandler(ws, session_id=1)
        # 模拟 dispatch
        await handler._dispatch(
            {"type": "audio_chunk", "data": _audio_b64(64)},
            db=MagicMock(),
            session=MagicMock(),
        )
        assert len(handler.ctx.audio_buffer) == 1

    @pytest.mark.asyncio
    async def test_audio_buffer_overflow_clears(self) -> None:
        from interview_service.realtime.ws_handler import (
            InterviewWSHandler,
            _AUDIO_BUFFER_MAX_BYTES,
        )

        ws = _make_mock_ws()
        handler = InterviewWSHandler(ws, session_id=1)
        # 一次塞超过上限的 chunk
        huge = _audio_b64(_AUDIO_BUFFER_MAX_BYTES + 1024)
        await handler._dispatch(
            {"type": "audio_chunk", "data": huge},
            db=MagicMock(),
            session=MagicMock(),
        )
        # 超阈应当被清空并发 error
        assert handler.ctx.audio_buffer == []
        # 至少一次 error 事件
        ws.send_json.assert_called()
        sent = [c.args[0] for c in ws.send_json.call_args_list]
        assert any(e.get("type") == "error" for e in sent)


class TestDispatchUnknownType:
    @pytest.mark.asyncio
    async def test_unknown_type_no_op(self) -> None:
        from interview_service.realtime.ws_handler import InterviewWSHandler

        ws = _make_mock_ws()
        handler = InterviewWSHandler(ws, session_id=1)
        # 未知消息不应抛错
        await handler._dispatch(
            {"type": "nonsense_unknown"},
            db=MagicMock(),
            session=MagicMock(),
        )
        ws.send_json.assert_not_called()

    @pytest.mark.asyncio
    async def test_pong_no_op(self) -> None:
        from interview_service.realtime.ws_handler import InterviewWSHandler

        ws = _make_mock_ws()
        handler = InterviewWSHandler(ws, session_id=1)
        await handler._dispatch(
            {"type": "pong", "t": 123},
            db=MagicMock(),
            session=MagicMock(),
        )
        ws.send_json.assert_not_called()


class TestTurnState:
    def test_values(self) -> None:
        assert TurnState.USER_SPEAKING.value == "USER_SPEAKING"
        assert TurnState.AI_SPEAKING.value == "AI_SPEAKING"
        assert TurnState.PROCESSING.value == "PROCESSING"
        assert TurnState.IDLE.value == "IDLE"


class TestSetTurn:
    @pytest.mark.asyncio
    async def test_set_turn_emits_turn_state_event(self) -> None:
        from interview_service.realtime.ws_handler import InterviewWSHandler

        ws = _make_mock_ws()
        handler = InterviewWSHandler(ws, session_id=1)
        await handler.set_turn(TurnState.USER_SPEAKING)
        assert handler.ctx.turn_state == TurnState.USER_SPEAKING
        ws.send_json.assert_called_once_with(
            {"type": "turn_state", "state": "USER_SPEAKING"}
        )


class TestSessionConnectionMutex:
    @pytest.mark.asyncio
    async def test_claim_kicks_previous_handler(self) -> None:
        """新连接 claim 同一 session 时应标记并关闭旧连接。"""
        from interview_service.realtime import ws_handler as ws_mod

        ws_mod.reset_session_registry_for_tests()
        old_ws = _make_mock_ws()
        new_ws = _make_mock_ws()
        old_ws.close = AsyncMock()
        new_ws.close = AsyncMock()

        old_h = ws_mod.InterviewWSHandler(old_ws, session_id=42)
        new_h = ws_mod.InterviewWSHandler(new_ws, session_id=42)

        await ws_mod.claim_session_connection(old_h)
        assert old_h._superseded is False
        assert ws_mod._active_handlers[42] is old_h

        await ws_mod.claim_session_connection(new_h)
        assert old_h._superseded is True
        assert new_h._superseded is False
        assert ws_mod._active_handlers[42] is new_h
        old_ws.close.assert_awaited()
        # 旧连接应收到 error 提示
        sent = [c.args[0] for c in old_ws.send_json.call_args_list]
        assert any(e.get("type") == "error" for e in sent)

        # 释放被顶替的旧 handler 不应误删新连接
        await ws_mod.release_session_connection(old_h)
        assert ws_mod._active_handlers[42] is new_h

        await ws_mod.release_session_connection(new_h)
        assert 42 not in ws_mod._active_handlers

    @pytest.mark.asyncio
    async def test_different_sessions_independent(self) -> None:
        from interview_service.realtime import ws_handler as ws_mod

        ws_mod.reset_session_registry_for_tests()
        h1 = ws_mod.InterviewWSHandler(_make_mock_ws(), session_id=1)
        h2 = ws_mod.InterviewWSHandler(_make_mock_ws(), session_id=2)
        await ws_mod.claim_session_connection(h1)
        await ws_mod.claim_session_connection(h2)
        assert h1._superseded is False
        assert h2._superseded is False
        assert ws_mod._active_handlers[1] is h1
        assert ws_mod._active_handlers[2] is h2
        await ws_mod.release_session_connection(h1)
        await ws_mod.release_session_connection(h2)


class TestTraceId:
    @pytest.mark.asyncio
    async def test_handle_sets_trace_id(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """handle() 入口应注入 ws-{session}-{uuid} 形式的 trace_id。"""
        from shared.core.logging import get_trace_id
        from interview_service.realtime import ws_handler as ws_mod
        from shared.capabilities.ai.llm.client import LLMClient

        captured_tid: list[str] = []

        class _StubRunner:
            async def stream_opening(self, db):
                if False:
                    yield  # 空异步生成器

        monkeypatch.setattr(LLMClient, "from_db", classmethod(lambda cls, db: MagicMock(api_key="")))
        monkeypatch.setattr(
            "interview_service.realtime.context.InterviewOrchestrator", MagicMock()
        )
        monkeypatch.setattr(
            "interview_service.realtime.connection_lifecycle.InterviewRunner",
            lambda *a, **kw: _StubRunner(),
        )
        # 模拟 db.query 拿到 session
        class _StubSession:
            id = 1
            status = "completed"  # 让 handle 早退不发 opening
            access_token = "test-token-aaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = _StubSession()
        # handle() 定义在 connection_lifecycle 模块，须 patch 该模块的 SessionLocal
        monkeypatch.setattr(
            "interview_service.realtime.connection_lifecycle.SessionLocal", lambda: mock_db
        )

        ws = _make_mock_ws()
        handler = ws_mod.InterviewWSHandler(
            ws, session_id=1, access_token=_StubSession.access_token
        )
        # 由于 status=completed，handle 会先发送 error 然后 return
        await handler.handle()

        # 现在 trace_id 应已经被注入（set_trace_id 是模块级 ContextVar）
        tid = get_trace_id()
        assert tid.startswith("ws-1-")
        captured_tid.append(tid)


class TestFailAndClose:
    """鉴权/状态失败路径应统一发 error + ws.close(4401)。"""

    @staticmethod
    def _patch_session_db(
        monkeypatch: pytest.MonkeyPatch, session: object | None
    ) -> MagicMock:
        """patch connection_lifecycle 模块的 SessionLocal（handle 定义处）。"""
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = session
        monkeypatch.setattr(
            "interview_service.realtime.connection_lifecycle.SessionLocal", lambda: mock_db
        )
        return mock_db

    @pytest.mark.asyncio
    async def test_wrong_token_closes_4401(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from interview_service.realtime.ws_handler import InterviewWSHandler

        class _StubSession:
            id = 1
            status = "pending"
            access_token = "correct-token-aaaaaaaaaaaaaaaaaaaa"

        self._patch_session_db(monkeypatch, _StubSession())

        ws = _make_mock_ws()
        handler = InterviewWSHandler(ws, session_id=1, access_token="wrong-token")
        await handler.handle()

        # 先发 error，再以 4401 关闭
        assert ws.send_json.await_count == 1
        assert ws.send_json.await_args[0][0]["type"] == "error"
        ws.close.assert_awaited_once_with(code=4401)

    @pytest.mark.asyncio
    async def test_missing_session_closes_4401(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from interview_service.realtime.ws_handler import InterviewWSHandler

        self._patch_session_db(monkeypatch, None)

        ws = _make_mock_ws()
        handler = InterviewWSHandler(ws, session_id=999)
        await handler.handle()

        assert ws.send_json.await_count == 1
        assert ws.send_json.await_args[0][0]["type"] == "error"
        ws.close.assert_awaited_once_with(code=4401)

    @pytest.mark.asyncio
    async def test_finished_session_closes_4401(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from interview_service.realtime.ws_handler import InterviewWSHandler

        class _StubSession:
            id = 1
            status = "completed"
            access_token = "test-token-aaaaaaaaaaaaaaaaaaaaaaaaaaaa"

        self._patch_session_db(monkeypatch, _StubSession())

        ws = _make_mock_ws()
        handler = InterviewWSHandler(
            ws, session_id=1, access_token="test-token-aaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        )
        await handler.handle()

        # 状态检查已前置到 claim/初始化之前：completed 会话直接发"面试已结束"
        assert ws.send_json.await_count == 1
        err = ws.send_json.await_args[0][0]
        assert err["type"] == "error"
        assert err["message"] == "面试已结束"
        ws.close.assert_awaited_once_with(code=4401)

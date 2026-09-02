"""WS / 面试路径加固回归：PCM 上限、限流、打断世代、纯中文 STT 快路径。"""

from __future__ import annotations

from shared.capabilities.voice.stt import SttCredentials, SttResult
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from shared.core.ratelimit import reset_rate_limit, try_rate_limit_by_id
from interview_service.realtime import ws_handler
from interview_service.realtime.voice.pipeline import (
    _pick_stt_text,
    _should_skip_whisper,
)
from interview_service.realtime.core.events import TurnState
from interview_service.services.interview.events import EventKind, StreamEvent


def test_pcm_limit_constant():
    assert ws_handler._AUDIO_BUFFER_MAX_BYTES == 5 * 1024 * 1024


def test_try_rate_limit_by_id_blocks_after_limit():
    reset_rate_limit("llm_test_ws")
    for _ in range(3):
        assert try_rate_limit_by_id(
            key="llm_test_ws", client_id="s1", limit=3, window_seconds=60
        )
    assert not try_rate_limit_by_id(
        key="llm_test_ws", client_id="s1", limit=3, window_seconds=60
    )
    reset_rate_limit("llm_test_ws")


def test_should_skip_whisper_disabled():
    # 准确率优先：不再跳过 ASR
    assert _should_skip_whisper("这是一段足够长的中文回答内容") is False
    assert _should_skip_whisper("短") is False


def test_pick_stt_prefers_whisper_on_english():
    got = _pick_stt_text("啊啊啊啊", "I used React and Docker")
    assert "React" in got


def _make_handler() -> ws_handler.InterviewWSHandler:
    ws = MagicMock()
    ws.accept = AsyncMock()
    ws.send_json = AsyncMock()
    ws.receive_json = AsyncMock()
    ws.close = AsyncMock()
    return ws_handler.InterviewWSHandler(ws, session_id=1)


class TestBargeEpoch:
    def test_can_start_after_barge_invalidates_busy(self) -> None:
        h = _make_handler()
        epoch = h._begin_user_turn()
        assert epoch is not None
        assert h.ctx.turn_busy is True
        assert not h._can_start_user_turn()
        # 模拟 barge：推进 stream epoch，不盲清 busy
        h.ctx.stream_epoch += 1
        assert h._can_start_user_turn()
        new_epoch = h._begin_user_turn()
        assert new_epoch == h.ctx.stream_epoch
        # 旧回合结束不得清掉新回合的锁
        h._end_user_turn(epoch)
        assert h.ctx.turn_busy is True
        h._end_user_turn(new_epoch)
        assert h.ctx.turn_busy is False

    @pytest.mark.asyncio
    async def test_barge_bumps_playback_generation(self) -> None:
        h = _make_handler()
        h.ctx.turn_state = TurnState.AI_SPEAKING
        h.ctx.awaiting_playback_gen = 3
        h.ctx.playback_generation = 3
        h.ctx.stream_epoch = 1
        h.ctx.tts_queue.clear = AsyncMock()
        await h._on_candidate_barge_in()
        assert h.ctx.stream_epoch == 2
        assert h.ctx.playback_generation == 4
        assert h.ctx.awaiting_playback_gen == 4
        assert h.ctx.turn_state == TurnState.USER_SPEAKING
        h.ctx.tts_queue.clear.assert_awaited()
        sent = [c.args[0] for c in h.ws.send_json.call_args_list]
        assert any(e.get("type") == "tts_interrupted" for e in sent)
        interrupted = next(e for e in sent if e.get("type") == "tts_interrupted")
        assert interrupted.get("playback_generation") == 4

    @pytest.mark.asyncio
    async def test_stream_returns_none_after_barge_epoch(self) -> None:
        h = _make_handler()
        h.ctx.stream_epoch = 5
        h.ctx.tts_queue.enqueue = AsyncMock()
        h.ctx.tts_queue.flush_remainder = AsyncMock()

        async def events():
            # 模拟流中途被 barge：推进 epoch
            h.ctx.stream_epoch += 1
            yield StreamEvent(
                kind=EventKind.TOKEN,
                token="你好",
            )
            yield StreamEvent(
                kind=EventKind.TURN_COMPLETE,
                content="你好",
                phase_id="intro",
                is_complete=False,
            )

        last = await h._stream_events_with_tts(events(), auto_hint=False)
        assert last is None
        h.ctx.tts_queue.enqueue.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_process_user_text_skips_open_mic_after_barge(self) -> None:
        h = _make_handler()
        h.ctx.runner = MagicMock()
        h._open_mic_after_playback = AsyncMock()
        start_epoch = h.ctx.stream_epoch

        async def fake_stream(*_a, **_k):
            h.ctx.stream_epoch = start_epoch + 1
            h.ctx.turn_state = TurnState.USER_SPEAKING
            return None

        h._stream_events_with_tts = fake_stream  # type: ignore[method-assign]
        h._consume_runner_turn = MagicMock(return_value=None)
        await h._process_user_text("答", {}, MagicMock(), MagicMock())
        h._open_mic_after_playback.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_open_mic_aborts_when_epoch_changed(self) -> None:
        h = _make_handler()
        h.ctx.tts_sent_this_turn = False
        h.ctx.turn_state = TurnState.AI_SPEAKING
        epoch = h.ctx.stream_epoch

        async def wait_then_barge():
            h.ctx.stream_epoch = epoch + 1
            h.ctx.turn_state = TurnState.USER_SPEAKING

        h._wait_client_playback = wait_then_barge  # type: ignore[method-assign]
        h.set_turn = AsyncMock()
        await h._open_mic_after_playback()
        h.set_turn.assert_not_awaited()


class TestSttAlwaysRuns:
    @pytest.mark.asyncio
    async def test_asr_always_called_for_pcm(self) -> None:
        h = _make_handler()
        h.ctx.turn_state = TurnState.USER_SPEAKING
        h.ctx.agent = None
        h.ctx.llm = MagicMock(api_base="https://api.openai.com/v1", api_key="sk-t")
        h.ctx.stt_creds = SttCredentials(
            provider="openai_compat",
            api_base=h.ctx.llm.api_base,
            api_key="sk-stt",
            model="whisper-1",
        )
        h._process_user_text = AsyncMock()
        with patch(
            "interview_service.realtime.turn.stt_finish.transcribe_utterance_result",
            new_callable=AsyncMock,
            return_value=SttResult(text="这是一段足够长的中文技术回答内容", provider="local"),
        ) as mock_tr:
            await h._on_user_turn_end(
                {
                    "text": "这是一段足够长的中文技术回答内容",
                    "pcm": "AAAA",
                    "sample_rate": 16000,
                },
                db=MagicMock(),
                session=MagicMock(),
            )
            mock_tr.assert_awaited()
            h._process_user_text.assert_awaited()

    @pytest.mark.asyncio
    async def test_asr_preferred_for_english_mix(self) -> None:
        h = _make_handler()
        h.ctx.turn_state = TurnState.USER_SPEAKING
        h.ctx.agent = None
        h.ctx.llm = MagicMock(api_base="https://api.openai.com/v1", api_key="sk-t")
        h.ctx.stt_creds = SttCredentials(
            provider="openai_compat",
            api_base=h.ctx.llm.api_base,
            api_key="sk-stt",
            model="whisper-1",
        )
        h._process_user_text = AsyncMock()
        with patch(
            "interview_service.realtime.turn.stt_finish.transcribe_utterance_result",
            new_callable=AsyncMock,
            return_value=SttResult(text="I used React hooks", provider="local"),
        ) as mock_tr:
            await h._on_user_turn_end(
                {
                    "text": "我用 React hooks 做过",
                    "pcm": "AAAA",
                    "sample_rate": 16000,
                },
                db=MagicMock(),
                session=MagicMock(),
            )
            mock_tr.assert_awaited()
            assert h._process_user_text.await_args.args[0] == "I used React hooks"

"""云端 STT 与择优逻辑回归。"""

from __future__ import annotations

from shared.capabilities.voice.stt import SttCredentials, SttResult
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from interview_service.realtime import ws_handler
from interview_service.realtime.voice.pipeline import _pick_stt_text, _should_skip_whisper
from interview_service.realtime.core.events import TurnState
from shared.capabilities.voice.stt.cloud import is_local_stt_model, resolve_cloud_stt_model


def test_resolve_cloud_model_maps_local_sizes():
    assert resolve_cloud_stt_model("base") == "whisper-1"
    assert resolve_cloud_stt_model("small") == "whisper-1"
    assert resolve_cloud_stt_model("whisper-1") == "whisper-1"
    assert resolve_cloud_stt_model("gpt-4o-mini-transcribe") == "gpt-4o-mini-transcribe"
    assert is_local_stt_model("base")
    assert not is_local_stt_model("whisper-1")


def test_pick_stt_prefers_asr_over_browser_chinese():
    # 浏览器误听「美食馆」，云端正确「面试官」
    got = _pick_stt_text(
        "你好美食馆都是能听到的",
        "你好面试官都能听到的",
    )
    assert "面试官" in got
    assert "美食馆" not in got


def test_should_skip_whisper_always_false():
    assert _should_skip_whisper("这是一段足够长的中文回答内容") is False


def test_pick_stt_prefers_whisper_on_english():
    got = _pick_stt_text("啊啊啊啊", "I used React and Docker")
    assert "React" in got


def _make_handler() -> ws_handler.InterviewWSHandler:
    ws = MagicMock()
    ws.accept = AsyncMock()
    ws.send_json = AsyncMock()
    ws.receive_json = AsyncMock()
    h = ws_handler.InterviewWSHandler(ws, session_id=1)
    h.ctx.llm = MagicMock()
    h.ctx.llm.api_base = "https://api.openai.com/v1"
    h.ctx.llm.api_key = "sk-test"

    h.ctx.stt_creds = SttCredentials(
        provider="openai_compat",
        api_base="https://api.openai.com/v1",
        api_key="sk-stt-only",
        model="whisper-1",
    )
    h.ctx.whisper_model = "whisper-1"
    return h


class TestCloudSttPath:
    @pytest.mark.asyncio
    async def test_user_turn_uses_cloud_asr(self) -> None:
        h = _make_handler()
        h.ctx.turn_state = TurnState.USER_SPEAKING
        h.ctx.agent = None
        h._process_user_text = AsyncMock()
        with patch(
            "interview_service.realtime.turn.stt_finish.transcribe_utterance_result",
            new_callable=AsyncMock,
            return_value=SttResult(text="你好面试官都能听到的", provider="local"),
        ) as mock_tr:
            await h._on_user_turn_end(
                {
                    "text": "你好美食馆都是能听到的",
                    "pcm": "AAAA",
                    "sample_rate": 16000,
                },
                db=MagicMock(),
                session=MagicMock(),
            )
            mock_tr.assert_awaited()
            # 必须传入独立 creds，不得静默用思考 Key
            kwargs = mock_tr.await_args.kwargs
            assert kwargs.get("creds") is h.ctx.stt_creds
            assert h.ctx.stt_creds.api_key == "sk-stt-only"
            assert h.ctx.stt_creds.api_key != h.ctx.llm.api_key
            args = h._process_user_text.await_args
            assert args.args[0] == "你好面试官都能听到的"

    @pytest.mark.asyncio
    async def test_transcribe_utterance_cloud_first(self) -> None:
        from shared.capabilities.voice.stt import transcribe_utterance

        with (
            patch(
                "shared.capabilities.voice.stt.openai_compat.transcribe_pcm_cloud",
                new_callable=AsyncMock,
                return_value="云端结果正确",
            ) as cloud,
            patch(
                "shared.capabilities.voice.stt.local.transcribe_pcm_base64_async",
                new_callable=AsyncMock,
                return_value="本地",
            ) as local,
        ):
            text = await transcribe_utterance(
                "AAAA",
                creds=SttCredentials(
                    provider="openai_compat",
                    api_base="https://api.openai.com/v1",
                    api_key="sk-x",
                    model="whisper-1",
                ),
            )
            assert text == "云端结果正确"
            cloud.assert_awaited()
            local.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_transcribe_falls_back_local(self) -> None:
        from shared.capabilities.voice.stt import transcribe_utterance

        with (
            patch(
                "shared.capabilities.voice.stt.openai_compat.transcribe_pcm_cloud",
                new_callable=AsyncMock,
                return_value="",
            ),
            patch(
                "shared.capabilities.voice.stt.local.transcribe_pcm_base64_async",
                new_callable=AsyncMock,
                return_value="本地回退",
            ) as local,
        ):
            text = await transcribe_utterance(
                "AAAA",
                creds=SttCredentials(
                    provider="openai_compat",
                    api_base="https://api.openai.com/v1",
                    api_key="sk-x",
                    model="whisper-1",
                ),
            )
            assert text == "本地回退"
            local.assert_awaited()

    @pytest.mark.asyncio
    async def test_no_llm_key_without_asr_creds_goes_local(self) -> None:
        """未配置独立 ASR 时不得用思考 Key；无 creds 旧参无 Key → 本地。"""
        from shared.capabilities.voice.stt import transcribe_utterance

        with patch(
            "shared.capabilities.voice.stt.transcribe_local_async",
            new_callable=AsyncMock,
            return_value="仅本地",
        ) as local:
            text = await transcribe_utterance("AAAA", model="base")
            assert text == "仅本地"
            local.assert_awaited()

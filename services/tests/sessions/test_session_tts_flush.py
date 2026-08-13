"""会话修复：TTS flush_remainder 真正排空队列。"""

from __future__ import annotations

import asyncio

import pytest


@pytest.mark.asyncio
async def test_flush_waits_for_all_enqueued(monkeypatch: pytest.MonkeyPatch) -> None:
    from interview_service.realtime.ws_handler import _SentenceTTSQueue

    order: list[str] = []
    delays = {"你好。": 0.05, "第二句。": 0.05, "第三句。": 0.05}

    async def slow_synth(sentence: str, *, creds=None, rate="+0%", pitch="+0Hz") -> str:
        await asyncio.sleep(delays.get(sentence, 0.01))
        return f"audio:{sentence}"

    monkeypatch.setattr(
        "interview_service.realtime.ws_handler.synthesize_speech",
        slow_synth,
    )

    async def send_cb(msg_type, **payload):
        order.append(payload["sentence"])

    q = _SentenceTTSQueue()
    await q.start(send_cb)
    await q.enqueue("你好。")
    await q.enqueue("第二句。")
    await q.enqueue("第三句。")
    await q.flush_remainder("")
    # flush 返回后队列应已全部处理
    assert order == ["你好。", "第二句。", "第三句。"]
    await q.stop()


@pytest.mark.asyncio
async def test_flush_remainder_enqueues_trailing(monkeypatch: pytest.MonkeyPatch) -> None:
    from interview_service.realtime.ws_handler import _SentenceTTSQueue

    sent: list[str] = []

    async def synth(sentence: str, *, creds=None, rate="+0%", pitch="+0Hz") -> str:
        return f"a:{sentence}"

    monkeypatch.setattr("interview_service.realtime.ws_handler.synthesize_speech", synth)

    async def send_cb(msg_type, **payload):
        sent.append(payload["sentence"])

    q = _SentenceTTSQueue()
    await q.start(send_cb)
    await q.flush_remainder("尾句。")
    await q.stop()
    assert sent == ["尾句。"]

"""TTS 串行队列单元测试。

通过 patch 掉 synthesize_speech，验证队列串行播放、不与入队相互阻塞。
"""

from __future__ import annotations

import asyncio

from interview_service.realtime.tts_queue import _SentenceTTSQueue


async def _fake_synth(sentence: str, *, creds=None, rate="+0%", pitch="+0Hz") -> str:
    return f"audio:{sentence}"


async def test_enqueue_processes_in_order(monkeypatch) -> None:
    monkeypatch.setattr(
        "interview_service.realtime.tts_queue.synthesize_speech", _fake_synth,
    )

    sent: list[tuple[str, str]] = []

    async def send_cb(msg_type, **payload):
        sent.append((payload["sentence"], payload["data"]))

    q = _SentenceTTSQueue()
    await q.start(send_cb)
    await q.enqueue("你好。")
    await q.enqueue("欢迎参加面试。")
    await q.flush_remainder("")
    await q.stop()

    assert sent == [
        ("你好。", "audio:你好。"),
        ("欢迎参加面试。", "audio:欢迎参加面试。"),
    ]


async def test_enqueue_skips_empty(monkeypatch) -> None:
    monkeypatch.setattr(
        "interview_service.realtime.tts_queue.synthesize_speech", _fake_synth,
    )
    sent: list[str] = []

    async def send_cb(msg_type, **payload):
        sent.append(payload["sentence"])

    q = _SentenceTTSQueue()
    await q.start(send_cb)
    await q.enqueue("   ")
    await q.enqueue("")
    await q.flush_remainder("  ")
    await q.stop()

    assert sent == []


async def test_enqueue_does_not_block_producer(monkeypatch) -> None:
    """入队操作应是非阻塞的，生产者不会被 TTS 合成延迟。"""

    async def slow_synth(sentence, *, creds=None, rate="+0%", pitch="+0Hz"):
        await asyncio.sleep(0.2)
        return f"audio:{sentence}"

    monkeypatch.setattr(
        "interview_service.realtime.tts_queue.synthesize_speech", slow_synth,
    )

    sent: list[str] = []

    async def send_cb(msg_type, **payload):
        sent.append(payload["sentence"])

    q = _SentenceTTSQueue()
    await q.start(send_cb)

    import time

    t0 = time.monotonic()
    for i in range(5):
        await q.enqueue(f"句{i}。")
    elapsed = time.monotonic() - t0

    # 5 次入队不应被 TTS 合成阻塞，应 < 0.1s
    assert elapsed < 0.1, f"入队耗时过长: {elapsed:.3f}s"

    await q.flush_remainder("")
    await q.stop()

    assert len(sent) == 5

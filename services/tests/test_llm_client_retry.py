"""``app.services.llm.client`` 单元测试：重试 + SSRF 拒绝。

通过 monkeypatch + mock httpx.AsyncClient 验证：

- 4xx 直接抛，不重试；
- 5xx/429 指数退避重试至 max_retries 次；
- allow_local_llm=False 时循环回环被拒；
- allow_local_llm=True 时本机 127.0.0.1:9999 放行。
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from shared.core.security import UnsafeURLError


def _patch_settings(monkeypatch: pytest.MonkeyPatch, *, allow_local: bool) -> None:
    """替换 client 模块内的 get_settings 为 MagicMock；allow_local_llm 可控。"""
    s = MagicMock()
    s.allow_local_llm = allow_local
    s.effective_embeddings_base = "https://api.openai.com/v1"
    s.effective_embeddings_key = "sk-test"
    s.effective_embeddings_model = "text-embedding-3-small"
    s.is_prod = not allow_local
    # client 拆包后 get_settings 分布在 llm_client_ext / base / openai_transport 三个子模块
    monkeypatch.setattr("shared.capabilities.ai.llm.client.llm_client_ext.get_settings", lambda: s)
    monkeypatch.setattr("shared.capabilities.ai.llm.client.base.get_settings", lambda: s)
    monkeypatch.setattr("shared.capabilities.ai.llm.client.openai_transport.get_settings", lambda: s)


def _make_client(monkeypatch: pytest.MonkeyPatch, *, allow_local: bool) -> Any:
    _patch_settings(monkeypatch, allow_local=allow_local)
    from shared.capabilities.ai.llm.client import LLMClient

    return LLMClient(
        api_base="https://api.openai.com/v1",
        api_key="sk-test-key",
        model="gpt-4o",
    )


@pytest.mark.asyncio
async def test_chat_4xx_no_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _make_client(monkeypatch, allow_local=False)
    # 本测试聚焦重试语义：URL 校验放行（域名真实 DNS 在不同环境解析结果不同）
    monkeypatch.setattr("shared.capabilities.ai.llm.client.llm_client.is_safe_http_url", lambda *a, **kw: True)
    http_client = AsyncMock()
    fake_resp = MagicMock(spec=httpx.Response)
    fake_resp.status_code = 400
    fake_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
        "400", request=MagicMock(), response=fake_resp
    )
    http_client.post = AsyncMock(return_value=fake_resp)
    with patch("shared.capabilities.ai.llm.client.openai_transport.make_pinned_async_client") as ac:
        ac.return_value.__aenter__.return_value = http_client
        ac.return_value.__aexit__.return_value = False
        with pytest.raises(httpx.HTTPStatusError):
            await client.chat([{"role": "user", "content": "hi"}])
    # 4xx 不重试：只调用 1 次
    assert http_client.post.await_count == 1


@pytest.mark.asyncio
async def test_chat_429_retries_then_returns(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _make_client(monkeypatch, allow_local=False)
    # 同 test_chat_4xx_no_retry：URL 校验放行，聚焦重试语义
    monkeypatch.setattr("shared.capabilities.ai.llm.client.llm_client.is_safe_http_url", lambda *a, **kw: True)

    succ = MagicMock(spec=httpx.Response)
    succ.status_code = 200
    succ.json.return_value = {"choices": [{"message": {"content": "ok"}}]}
    succ.raise_for_status = MagicMock()

    http_client = AsyncMock()
    http_client.post = AsyncMock(
        side_effect=[
            httpx.HTTPStatusError(
                "429", request=MagicMock(), response=MagicMock(status_code=429)
            ),
            httpx.HTTPStatusError(
                "429", request=MagicMock(), response=MagicMock(status_code=429)
            ),
            succ,
        ]
    )
    with patch("shared.capabilities.ai.llm.client.openai_transport.make_pinned_async_client") as ac:
        ac.return_value.__aenter__.return_value = http_client
        ac.return_value.__aexit__.return_value = False
        with patch("shared.capabilities.ai.llm.client.base.asyncio.sleep", new=AsyncMock()):
            text = await client.chat([{"role": "user", "content": "hi"}])
    assert text == "ok"
    assert http_client.post.await_count == 3


@pytest.mark.asyncio
async def test_chat_blocks_loopback_in_prod(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _make_client(monkeypatch, allow_local=False)
    client.api_base = "http://127.0.0.1:9999/v1"
    with pytest.raises(UnsafeURLError):
        await client.chat([{"role": "user", "content": "hi"}])


@pytest.mark.asyncio
async def test_chat_allows_loopback_in_dev(monkeypatch: pytest.MonkeyPatch) -> None:
    """allow_local=True 时 127.0.0.1:9999 通过 SSRF 检查进入请求。"""
    client = _make_client(monkeypatch, allow_local=True)
    client.api_base = "http://127.0.0.1:9999/v1"
    succ = MagicMock(spec=httpx.Response)
    succ.status_code = 200
    succ.json.return_value = {"choices": [{"message": {"content": "ok"}}]}
    succ.raise_for_status = MagicMock()
    http_client = AsyncMock()
    http_client.post = AsyncMock(return_value=succ)
    with patch("shared.capabilities.ai.llm.client.openai_transport.make_pinned_async_client") as ac:
        ac.return_value.__aenter__.return_value = http_client
        ac.return_value.__aexit__.return_value = False
        text = await client.chat([{"role": "user", "content": "hi"}])
    assert text == "ok"


# ── 流式工具轮组装器（chat_message_stream 的事件 → message 装配）──────────


def test_openai_round_assembler_joins_fragments() -> None:
    """tool_calls 的 id/name/arguments 分片按 index 拼接，组装与非流式同构 message。"""
    from shared.capabilities.ai.llm.client.assemblers import _OpenAIRoundAssembler

    a = _OpenAIRoundAssembler()
    assert a.feed({"choices": [{"delta": {"reasoning_content": "思考"}}]}) == "思考"
    a.feed({"choices": [{"delta": {"content": "正文"}}]})
    a.feed({
        "choices": [{
            "delta": {
                "tool_calls": [
                    {"index": 0, "id": "c1", "function": {"name": "web_search", "arguments": '{"query": "面'}}
                ]
            }
        }]
    })
    a.feed({"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"arguments": '经"}'}}]}}]})
    msg = a.message()
    assert msg["content"] == "正文"
    assert msg["tool_calls"] == [
        {"id": "c1", "type": "function", "function": {"name": "web_search", "arguments": '{"query": "面经"}'}}
    ]


def test_anthropic_round_assembler_thinking_and_tool_use() -> None:
    """thinking_delta 即时回传；text 与 tool_use（partial_json 分片）缓冲组装。"""
    from shared.capabilities.ai.llm.client.assemblers import _AnthropicRoundAssembler

    a = _AnthropicRoundAssembler()
    a.feed({"type": "content_block_start", "index": 0, "content_block": {"type": "thinking"}})
    assert a.feed({
        "type": "content_block_delta", "index": 0,
        "delta": {"type": "thinking_delta", "thinking": "想一下"},
    }) == "想一下"
    a.feed({"type": "content_block_start", "index": 1, "content_block": {"type": "text"}})
    a.feed({"type": "content_block_delta", "index": 1, "delta": {"type": "text_delta", "text": "你好"}})
    a.feed({
        "type": "content_block_start", "index": 2,
        "content_block": {"type": "tool_use", "id": "t1", "name": "lookup"},
    })
    a.feed({"type": "content_block_delta", "index": 2, "delta": {"type": "input_json_delta", "partial_json": '{"q": '}})
    a.feed({"type": "content_block_delta", "index": 2, "delta": {"type": "input_json_delta", "partial_json": '"x"}'}})
    msg = a.message()
    assert msg["content"] == "你好"
    assert msg["tool_calls"] == [
        {"id": "t1", "type": "function", "function": {"name": "lookup", "arguments": '{"q": "x"}'}}
    ]


# ── 流式 429/5xx 重试（retry_stream：raise_for_status 须在重试判断之后）──────


def _stream_http_client(status_sequence):
    """构造按次序返回不同响应的 mock http client（c.stream 上下文）。"""
    http_client = MagicMock()
    calls = {"n": 0}

    def _ok_resp(lines):
        resp = MagicMock(spec=httpx.Response)
        resp.status_code = 200
        resp.request = MagicMock()
        resp.raise_for_status = MagicMock()

        def _aiter_lines():
            async def _gen():
                for line in lines:
                    yield line
            return _gen()

        resp.aiter_lines = _aiter_lines
        return resp

    def _err_resp(status: int):
        resp = MagicMock(spec=httpx.Response)
        resp.status_code = status
        resp.request = MagicMock()
        # aread 供 400/422 stream_options 检测分支读取 body；空 body 不含该字段
        resp.aread = AsyncMock(return_value=b"{}")
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            str(status), request=MagicMock(), response=resp
        )
        return resp

    def _stream(*args, **kwargs):
        idx = calls["n"]
        calls["n"] += 1
        item = status_sequence[min(idx, len(status_sequence) - 1)]
        ctx = MagicMock()
        if isinstance(item, int):
            ctx.__aenter__ = AsyncMock(return_value=_err_resp(item))
        else:
            ctx.__aenter__ = AsyncMock(return_value=_ok_resp(item))
        ctx.__aexit__ = AsyncMock(return_value=False)
        return ctx

    http_client.stream = _stream
    http_client.calls = calls
    return http_client


def _patch_retry_stream_env(monkeypatch: pytest.MonkeyPatch, http_client) -> None:
    _patch_settings(monkeypatch, allow_local=False)
    monkeypatch.setattr(
        "shared.capabilities.ai.llm.client.llm_client.is_safe_http_url",
        lambda *a, **kw: True,
    )
    sleeper = AsyncMock()

    async def _no_sleep(_seconds):
        return None

    sleeper.side_effect = _no_sleep
    monkeypatch.setattr("shared.capabilities.ai.llm.client.retry_stream.asyncio.sleep", sleeper)
    return sleeper


@pytest.mark.asyncio
async def test_chat_message_stream_429_retries_then_emits(monkeypatch: pytest.MonkeyPatch) -> None:
    """流式工具轮 429：未产出增量前指数退避重试，第二次成功。"""
    client = _make_client(monkeypatch, allow_local=False)
    http_client = _stream_http_client([429, ['data: {"choices":[{"delta":{"content":"hi"}}]}', "data: [DONE]"]])
    _patch_retry_stream_env(monkeypatch, http_client)

    with patch("shared.capabilities.ai.llm.client.retry_stream.make_pinned_async_client") as ac:
        ac.return_value.__aenter__.return_value = http_client
        ac.return_value.__aexit__.return_value = False
        events = []
        async for ev in client.chat_message_stream([{"role": "user", "content": "hi"}]):
            events.append(ev)

    assert http_client.calls["n"] == 2
    final = [e for e in events if e.get("type") == "message"]
    assert final and final[0]["message"]["content"] == "hi"


@pytest.mark.asyncio
async def test_chat_stream_429_retries_then_tokens(monkeypatch: pytest.MonkeyPatch) -> None:
    """流式文本 429：未产出 token 前重试，第二次吐正文。"""
    client = _make_client(monkeypatch, allow_local=False)
    http_client = _stream_http_client([429, ['data: {"choices":[{"delta":{"content":"hi"}}]}', "data: [DONE]"]])
    _patch_retry_stream_env(monkeypatch, http_client)

    with patch("shared.capabilities.ai.llm.client.retry_stream.make_pinned_async_client") as ac:
        ac.return_value.__aenter__.return_value = http_client
        ac.return_value.__aexit__.return_value = False
        tokens = []
        async for tok in client.chat_stream([{"role": "user", "content": "hi"}]):
            tokens.append(tok)

    assert http_client.calls["n"] == 2
    assert "".join(tokens) == "hi"


@pytest.mark.asyncio
async def test_chat_message_stream_4xx_no_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    """流式 4xx：不重试，直接抛出。"""
    client = _make_client(monkeypatch, allow_local=False)
    http_client = _stream_http_client([400])
    _patch_retry_stream_env(monkeypatch, http_client)

    with patch("shared.capabilities.ai.llm.client.retry_stream.make_pinned_async_client") as ac:
        ac.return_value.__aenter__.return_value = http_client
        ac.return_value.__aexit__.return_value = False
        with pytest.raises(httpx.HTTPStatusError):
            async for _ in client.chat_message_stream([{"role": "user", "content": "hi"}]):
                pass

    assert http_client.calls["n"] == 1

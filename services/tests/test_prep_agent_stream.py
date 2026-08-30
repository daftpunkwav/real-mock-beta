"""Prep Agent 流式事件序列:status / tool_step / ask_user / early 切片。"""

from __future__ import annotations

import asyncio
import json

import pytest

from agent_service.agents.prep.agent import (
    _ASK_USER_FALLBACK_REPLY,
    PREP_TOOL_DEFINITIONS,
    PrepAgent,
)


class _FakeLLM:
    """按脚本依次返回 chat_message 结果;``replies`` 支持多轮序列。"""

    def __init__(self, messages_reply=None, stream_tokens=(), replies=None):
        if replies is not None:
            self.replies = list(replies)
        else:
            self.replies = [messages_reply] if messages_reply is not None else []
        self.calls = 0
        self.stream_tokens = list(stream_tokens)

    async def chat_message(self, messages, temperature=0.7, tools=None, **kwargs):
        del messages, temperature, tools, kwargs
        idx = min(self.calls, len(self.replies) - 1)
        self.calls += 1
        return self.replies[idx]

    def chat_stream(self, messages, temperature=0.7, tools=None):
        async def _gen():
            for t in self.stream_tokens:
                yield t
        return _gen()


class _FakeSession:
    messages = "[]"
    resume_id = None
    target_company = ""
    token_usage = 0


class _FakeDB:
    def commit(self):
        pass

    def query(self, model):
        return _FakeQuery()


class _FakeQuery:
    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return None


def _collect(agen) -> list:
    async def run():
        return [item async for item in agen]
    return asyncio.run(run())


def test_tool_definitions_include_react_tools() -> None:
    names = {t["function"]["name"] for t in PREP_TOOL_DEFINITIONS}
    assert {"web_search", "ask_user", "take_note"} <= names


def test_chat_stream_ask_user_halts_with_event() -> None:
    llm = _FakeLLM(
        messages_reply={
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "c1",
                    "function": {
                        "name": "ask_user",
                        "arguments": json.dumps(
                            {"question": "目标岗位?", "options": ["后端", "算法"]},
                            ensure_ascii=False,
                        ),
                    },
                }
            ],
        }
    )
    agent = PrepAgent(_FakeSession(), llm)  # type: ignore[arg-type]

    async def run():
        out = []
        async for item in agent.chat_stream("帮我规划", _FakeDB()):  # type: ignore[arg-type]
            out.append(item)
        return out

    items = asyncio.run(run())
    types = [i["type"] for i in items if isinstance(i, dict)]
    assert "status" in types and "ask_user" in types
    ask = next(i for i in items if isinstance(i, dict) and i["type"] == "ask_user")
    assert ask["question"] == "目标岗位?"
    assert ask["options"] == ["后端", "算法"]
    # 弹窗后不再流式生成正式回答,只有固定引导语
    texts = [i for i in items if isinstance(i, str)]
    assert "".join(texts) == _ASK_USER_FALLBACK_REPLY
    # tool 消息已回填,消息序列保持配对
    tool_msgs = [m for m in agent.messages if m.get("role") == "tool"]
    assert tool_msgs and "弹窗" in tool_msgs[0]["content"]


def test_chat_stream_early_content_sliced_not_instant() -> None:
    long_answer = "很长的直接回答" * 50
    llm = _FakeLLM(messages_reply={"role": "assistant", "content": long_answer, "tool_calls": None})
    agent = PrepAgent(_FakeSession(), llm)  # type: ignore[arg-type]

    async def run():
        out = []
        async for item in agent.chat_stream("分析简历", _FakeDB()):  # type: ignore[arg-type]
            out.append(item)
        return out

    items = asyncio.run(run())
    texts = [i for i in items if isinstance(i, str)]
    assert len(texts) > 3, "early 内容应切片平滑输出而非一次性 yield"
    assert "".join(texts) == long_answer
    # 落库的最后一条 assistant 内容完整(其后可能跟工作记忆 system 块)
    assistant_msgs = [m for m in agent.messages if m.get("role") == "assistant"]
    assert assistant_msgs[-1]["content"] == long_answer


def test_chat_stream_clears_status_before_answer() -> None:
    long_answer = "正文" * 30
    llm = _FakeLLM(messages_reply={"role": "assistant", "content": long_answer, "tool_calls": None})
    agent = PrepAgent(_FakeSession(), llm)  # type: ignore[arg-type]

    async def run():
        return [item async for item in agent.chat_stream("hi", _FakeDB())]  # type: ignore[arg-type]

    items = asyncio.run(run())
    statuses = [i for i in items if isinstance(i, dict) and i["type"] == "status"]
    # 状态行以「正在分析」开头,且正文输出前以空串清除
    assert statuses[0]["text"] == "正在分析问题…"
    assert statuses[-1]["text"] == ""
    first_text_idx = next(i for i, x in enumerate(items) if isinstance(x, str))
    assert items.index(statuses[-1]) < first_text_idx


def test_chat_stream_ask_user_keeps_search_groups(monkeypatch) -> None:
    """ask_user 终止流时,先前已产生的搜索卡片事件不应丢失。"""

    def fake_search(query: str, max_results: int):
        return "[1] fake", [{"title": "t", "url": "https://example.com", "snippet": "s"}]

    monkeypatch.setattr(
        "agent_service.agents.prep.agent.web_search_with_hits", fake_search
    )
    search_reply = {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": "c0",
                "function": {
                    "name": "web_search",
                    "arguments": '{"query": "面经"}',
                },
            }
        ],
    }
    ask_reply = {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": "c1",
                "function": {
                    "name": "ask_user",
                    "arguments": '{"question": "选哪个?", "options": ["A", "B"]}',
                },
            }
        ],
    }
    llm = _FakeLLM(replies=[search_reply, ask_reply])
    agent = PrepAgent(_FakeSession(), llm)  # type: ignore[arg-type]

    async def run():
        return [item async for item in agent.chat_stream("hi", _FakeDB())]  # type: ignore[arg-type]

    items = asyncio.run(run())
    types = [i["type"] for i in items if isinstance(i, dict)]
    assert "search_results" in types, "ask_user 前的检索卡片必须补发"
    assert "ask_user" in types
    assert types.index("search_results") < types.index("ask_user")

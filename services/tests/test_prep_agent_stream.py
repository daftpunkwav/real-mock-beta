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
    """按脚本依次返回 chat_message / chat_stream 结果。"""

    def __init__(self, messages_reply=None, stream_tokens=()):
        self.messages_reply = messages_reply
        self.stream_tokens = list(stream_tokens)

    async def chat_message(self, messages, temperature=0.7, tools=None, **kwargs):
        del messages, temperature, tools, kwargs
        return self.messages_reply

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

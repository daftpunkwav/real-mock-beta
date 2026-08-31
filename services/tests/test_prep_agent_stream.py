"""Prep Agent 流式事件序列:status / tool_step / ask_user / usage / 收尾正文。"""

from __future__ import annotations

import asyncio
import json

import pytest

from agent_service.agents.prep.agent import (
    _ASK_USER_FALLBACK_REPLY,
    PREP_TOOL_DEFINITIONS,
    PrepAgent,
)
from shared.capabilities.ai.llm.usage import UsageAccumulator


class _FakeLLM:
    """按脚本依次返回 chat_message 结果;``replies`` 支持多轮序列。

    ``usage`` 模拟客户端上的用量累计（供应商回传时可得）；None 表示未回传。
    """

    def __init__(self, messages_reply=None, stream_tokens=(), replies=None, usage=None):
        if replies is not None:
            self.replies = list(replies)
        else:
            self.replies = [messages_reply] if messages_reply is not None else []
        self.calls = 0
        self.stream_calls = 0
        self.stream_tokens = list(stream_tokens)
        self.usage = usage

    async def chat_message(self, messages, temperature=0.7, tools=None, **kwargs):
        del messages, temperature, tools, kwargs
        idx = min(self.calls, len(self.replies) - 1)
        self.calls += 1
        return self.replies[idx]

    def chat_stream(self, messages, temperature=0.7, tools=None):
        del messages, temperature, tools
        self.stream_calls += 1

        async def _gen():
            for t in self.stream_tokens:
                yield t
        return _gen()


class _FakeSession:
    messages = "[]"
    resume_id = None
    target_company = ""
    token_usage = 0
    prompt_tokens = 0
    completion_tokens = 0
    cached_tokens = 0


class _FakeDB:
    def commit(self):
        pass

    def query(self, model):
        return _FakeQuery()


class _StreamFakeLLM(_FakeLLM):
    """带流式工具轮的假 LLM：``rounds[i]`` 为第 i 轮 chat_message_stream 事件。"""

    def __init__(self, rounds=None, **kwargs):
        super().__init__(**kwargs)
        self.rounds = list(rounds or [])

    async def chat_message_stream(self, messages, temperature=0.7, tools=None, **kwargs):
        del messages, temperature, tools, kwargs
        idx = min(self.calls, len(self.rounds) - 1)
        self.calls += 1
        for event in self.rounds[idx]:
            yield event


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
    # 落库的引导语消息应附带执行步骤(含 ask_user),刷新后可恢复执行过程
    assistant_msgs = [m for m in agent.messages if m.get("role") == "assistant"]
    last = assistant_msgs[-1]
    assert last["content"] == _ASK_USER_FALLBACK_REPLY
    assert any(s["name"] == "ask_user" for s in last["steps"])


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
        "agent_service.agents.prep.tools.web_search_with_hits", fake_search
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


def test_ask_user_options_normalizes_json_shapes() -> None:
    """LLM 不守 schema 把选项传成 dict/伪 JSON 时,弹窗事件必须给出干净文本。"""
    ask_reply = {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": "c1",
                "function": {
                    "name": "ask_user",
                    "arguments": json.dumps(
                        {
                            "question": "下一步?",
                            "options": [
                                {"description": "出一组 MCP 模拟题", "value": "quiz_mcp"},
                                "{description: '挑 1 个项目模拟连环追问', value: 'deep_dive'}",
                                "直接给学习路线",
                            ],
                        },
                        ensure_ascii=False,
                    ),
                },
            }
        ],
    }
    llm = _FakeLLM(messages_reply=ask_reply)
    agent = PrepAgent(_FakeSession(), llm)  # type: ignore[arg-type]

    async def run():
        return [item async for item in agent.chat_stream("hi", _FakeDB())]  # type: ignore[arg-type]

    items = asyncio.run(run())
    ask = next(i for i in items if isinstance(i, dict) and i["type"] == "ask_user")
    assert ask["options"] == [
        "出一组 MCP 模拟题",
        "挑 1 个项目模拟连环追问",
        "直接给学习路线",
    ]


def test_chat_stream_persists_steps_and_search_groups(monkeypatch) -> None:
    """执行步骤与检索卡片应随 assistant 消息落库,供刷新后恢复执行过程。"""

    def fake_search(query: str, max_results: int):
        return "[1] fake", [{"title": "t", "url": "https://example.com", "snippet": "s"}]

    monkeypatch.setattr(
        "agent_service.agents.prep.tools.web_search_with_hits", fake_search
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
    answer = "最终回答内容"
    answer_reply = {"role": "assistant", "content": answer, "tool_calls": None}
    # 工具轮之后模型正文直接作为最终回答切片回放,不再无工具二次生成
    llm = _FakeLLM(replies=[search_reply, answer_reply], stream_tokens=(answer,))
    agent = PrepAgent(_FakeSession(), llm)  # type: ignore[arg-type]

    async def run():
        return [item async for item in agent.chat_stream("hi", _FakeDB())]  # type: ignore[arg-type]

    items = asyncio.run(run())
    assert "".join(i for i in items if isinstance(i, str)) == answer
    assert llm.stream_calls == 0, "收尾正文来自循环返回,不应再触发无工具流式生成"

    assistant_msgs = [m for m in agent.messages if m.get("role") == "assistant"]
    last = assistant_msgs[-1]
    assert last["content"] == answer
    assert last["steps"] == [{"name": "web_search", "query": "面经"}]
    assert last["search_groups"][0]["query"] == "面经"


def test_chat_stream_emits_thinking_event_and_persists() -> None:
    """模型 reasoning 随 thinking 事件即时下发，并随 assistant 消息落库供刷新恢复。"""
    search_reasoning = "先记录薄弱点，再决定检索方向。"
    answer_reasoning = "整合观察结果，组织辅导回答。"
    search_reply = {
        "role": "assistant",
        "content": None,
        "reasoning": search_reasoning,
        "tool_calls": [
            {
                "id": "c0",
                "function": {
                    "name": "take_note",
                    "arguments": '{"kind": "note", "content": "x"}',
                },
            }
        ],
    }
    answer = "最终回答内容。" * 40
    answer_reply = {
        "role": "assistant",
        "content": answer,
        "reasoning": answer_reasoning,
        "tool_calls": None,
    }
    llm = _FakeLLM(replies=[search_reply, answer_reply])
    agent = PrepAgent(_FakeSession(), llm)  # type: ignore[arg-type]

    async def run():
        return [item async for item in agent.chat_stream("hi", _FakeDB())]  # type: ignore[arg-type]

    items = asyncio.run(run())
    thinking_events = [
        i for i in items if isinstance(i, dict) and i["type"] == "thinking"
    ]
    assert [e["content"] for e in thinking_events] == [
        search_reasoning,
        "\n\n" + answer_reasoning,
    ], "非流式整段 reasoning 逐轮下发，第二轮首段带轮间分隔"
    # 思考事件先于正文输出
    first_text_idx = next(i for i, x in enumerate(items) if isinstance(x, str))
    assert items.index(thinking_events[0]) < first_text_idx

    assistant_msgs = [m for m in agent.messages if m.get("role") == "assistant"]
    last = assistant_msgs[-1]
    assert last["content"] == answer
    assert search_reasoning in last["thinking"]
    assert answer_reasoning in last["thinking"]


def test_chat_stream_rounds_stream_thinking_deltas_and_persist() -> None:
    """流式工具轮：思考增量逐段下发（轮间补分隔），落库按轮拼接。"""
    answer = "最终回答内容。" * 40
    llm = _StreamFakeLLM(
        rounds=[
            [
                {"type": "reasoning", "text": "先记"},
                {"type": "reasoning", "text": "录要点"},
                {
                    "type": "message",
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "c0",
                                "type": "function",
                                "function": {
                                    "name": "take_note",
                                    "arguments": '{"kind": "note", "content": "x"}',
                                },
                            }
                        ],
                    },
                },
            ],
            [
                {"type": "reasoning", "text": "组织回答"},
                {
                    "type": "message",
                    "message": {"role": "assistant", "content": answer},
                },
            ],
        ]
    )
    agent = PrepAgent(_FakeSession(), llm)  # type: ignore[arg-type]

    async def run():
        return [item async for item in agent.chat_stream("hi", _FakeDB())]  # type: ignore[arg-type]

    items = asyncio.run(run())
    thinking_events = [
        i for i in items if isinstance(i, dict) and i["type"] == "thinking"
    ]
    assert [e["content"] for e in thinking_events] == [
        "先记",
        "录要点",
        "\n\n组织回答",
    ], "思考增量应逐段下发，第二轮首段带轮间分隔"
    first_text_idx = next(i for i, x in enumerate(items) if isinstance(x, str))
    assert items.index(thinking_events[0]) < first_text_idx
    assert "".join(i for i in items if isinstance(i, str)) == answer

    assistant_msgs = [m for m in agent.messages if m.get("role") == "assistant"]
    last = assistant_msgs[-1]
    assert last["content"] == answer
    # 持久化通道：按轮拼接、不带展示用分隔前缀
    assert last["thinking"] == "先记录要点\n\n组织回答"
    assert any(s["name"] == "take_note" for s in last["steps"])


def test_chat_stream_short_preamble_gets_drift_retry() -> None:
    """首轮无工具短旁白：循环注入一次性纠偏重试；模型坚持时按最终回答播报。"""
    preamble = "我并行搜一下近期面经，整理高频考点。"
    llm = _FakeLLM(replies=[{"role": "assistant", "content": preamble, "tool_calls": None}])
    agent = PrepAgent(_FakeSession(), llm)  # type: ignore[arg-type]

    async def run():
        return [item async for item in agent.chat_stream("hi", _FakeDB())]  # type: ignore[arg-type]

    items = asyncio.run(run())
    text = "".join(i for i in items if isinstance(i, str))
    assert text == preamble, "纠偏后仍只给短旁白时应按最终回答播报"
    assert llm.calls == 2, "短旁白触发恰好一次纠偏，不死循环"
    assert llm.stream_calls == 0


def test_chat_stream_final_content_no_extra_llm_call() -> None:
    """「说要提问却中断」回归：模型在工具轮后给出正文时,
    不得丢弃正文再发起无工具的第二次生成(该路径会复现内联工具漂移)。
    用过工具后的收尾正文是合法最终回答,即使很短也不触发纠偏重试。"""
    search_reply = {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": "c0",
                "function": {
                    "name": "take_note",
                    "arguments": '{"kind": "note", "content": "x"}',
                },
            }
        ],
    }
    drifting_reply = {
        "role": "assistant",
        "content": "我需要先和你确认两个关键决策，再继续：",
        "tool_calls": None,
    }
    llm = _FakeLLM(replies=[search_reply, drifting_reply], stream_tokens=())
    agent = PrepAgent(_FakeSession(), llm)  # type: ignore[arg-type]

    async def run():
        return [item async for item in agent.chat_stream("hi", _FakeDB())]  # type: ignore[arg-type]

    items = asyncio.run(run())
    text = "".join(i for i in items if isinstance(i, str))
    assert text == "我需要先和你确认两个关键决策，再继续："
    assert llm.calls == 2
    assert llm.stream_calls == 0


def test_chat_stream_inline_ask_user_rescued_as_modal() -> None:
    """模型把 ask_user 降级为正文内联 XML 时,必须抢救成弹窗事件而非静默清洗。"""
    search_reply = {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": "c0",
                "function": {
                    "name": "take_note",
                    "arguments": '{"kind": "note", "content": "x"}',
                },
            }
        ],
    }
    inline = (
        "我需要先和你确认两个关键决策，再继续：\n\n"
        '<tool_call>{"name": "ask_user", "arguments": '
        '{"question": "先讲哪个项目?", "options": ["agent-pulse", "agent-forge"]}}</tool_call>'
    )
    drifting_reply = {"role": "assistant", "content": inline, "tool_calls": None}
    llm = _FakeLLM(replies=[search_reply, drifting_reply])
    agent = PrepAgent(_FakeSession(), llm)  # type: ignore[arg-type]

    async def run():
        return [item async for item in agent.chat_stream("hi", _FakeDB())]  # type: ignore[arg-type]

    items = asyncio.run(run())
    asks = [i for i in items if isinstance(i, dict) and i["type"] == "ask_user"]
    assert len(asks) == 1, "内联 ask_user 必须转成弹窗事件"
    assert asks[0]["question"] == "先讲哪个项目?"
    assert asks[0]["options"] == ["agent-pulse", "agent-forge"]
    # 正文保留引导语,工具 XML 块被移除;落库内容与展示一致
    text = "".join(i for i in items if isinstance(i, str))
    assert "两个关键决策" in text
    assert "<tool_call>" not in text
    assistant_msgs = [m for m in agent.messages if m.get("role") == "assistant"]
    assert assistant_msgs[-1]["content"] == text


def test_chat_stream_emits_usage_event_and_persists() -> None:
    """供应商回传用量时:流末尾发 usage 事件,并累计进会话统计。"""
    usage = UsageAccumulator()
    usage.prompt_tokens = 900
    usage.completion_tokens = 120
    usage.cached_tokens = 700
    llm = _FakeLLM(
        messages_reply={"role": "assistant", "content": "直接回答", "tool_calls": None},
        usage=usage,
    )
    session = _FakeSession()
    agent = PrepAgent(session, llm)  # type: ignore[arg-type]

    async def run():
        return [item async for item in agent.chat_stream("hi", _FakeDB())]  # type: ignore[arg-type]

    items = asyncio.run(run())
    usage_events = [i for i in items if isinstance(i, dict) and i["type"] == "usage"]
    assert len(usage_events) == 1
    assert usage_events[0]["prompt_tokens"] == 900
    assert usage_events[0]["completion_tokens"] == 120
    assert usage_events[0]["cached_tokens"] == 700
    assert session.prompt_tokens == 900
    assert session.completion_tokens == 120
    assert session.cached_tokens == 700
    assert session.token_usage > 0


def test_chat_stream_without_usage_reports_no_usage_event() -> None:
    """供应商未回传用量:不发 usage 事件,也不写会话统计(不可知而非 0)。"""
    llm = _FakeLLM(
        messages_reply={"role": "assistant", "content": "直接回答", "tool_calls": None},
        usage=None,
    )
    session = _FakeSession()
    agent = PrepAgent(session, llm)  # type: ignore[arg-type]

    async def run():
        return [item async for item in agent.chat_stream("hi", _FakeDB())]  # type: ignore[arg-type]

    items = asyncio.run(run())
    assert not [i for i in items if isinstance(i, dict) and i["type"] == "usage"]
    assert session.prompt_tokens == 0


@pytest.mark.asyncio
async def test_execute_short_circuits_duplicate_tool_calls(monkeypatch) -> None:
    """本轮内相同参数的重复调用短路;失败的调用不缓存(允许换法重试)。"""
    calls: list[str] = []

    def fake_search(query: str, max_results: int):
        calls.append(query)
        return "[1] fake", []

    monkeypatch.setattr(
        "agent_service.agents.prep.tools.web_search_with_hits", fake_search
    )
    agent = PrepAgent(_FakeSession(), _FakeLLM(messages_reply={"role": "assistant", "content": "x"}))  # type: ignore[arg-type]
    execute = agent._build_execute(_FakeDB(), [], None, None)

    first = await execute("web_search", {"query": "面经"})
    second = await execute("web_search", {"query": "面经"})
    third = await execute("web_search", {"query": "React 面经"})

    assert calls == ["面经", "React 面经"], "相同参数只应真正执行一次"
    assert "重复调用" in second and "重复调用" not in first
    assert "重复调用" not in third


@pytest.mark.asyncio
async def test_execute_failed_call_not_cached(monkeypatch) -> None:
    """超时/检索失败的调用不进防重缓存:同参数重试仍会真正执行。"""
    attempts: list[str] = []

    import asyncio as _asyncio

    def slow_search(query: str, max_results: int):
        attempts.append(query)
        if len(attempts) == 1:
            raise _asyncio.TimeoutError()
        return "[1] ok", []

    monkeypatch.setattr(
        "agent_service.agents.prep.tools.web_search_with_hits", slow_search
    )
    agent = PrepAgent(_FakeSession(), _FakeLLM(messages_reply={"role": "assistant", "content": "x"}))  # type: ignore[arg-type]
    execute = agent._build_execute(_FakeDB(), [], None, None)

    first = await execute("web_search", {"query": "面经"})
    second = await execute("web_search", {"query": "面经"})

    assert attempts == ["面经", "面经"], "失败后同参数重试应放行"
    assert "超时" in first and "重复调用" not in second

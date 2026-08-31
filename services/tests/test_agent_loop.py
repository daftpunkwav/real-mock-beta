"""共享 Agent 循环与工作记忆。"""

from __future__ import annotations

import asyncio

import pytest

from shared.capabilities.ai.agent import WorkingMemory, run_agent_loop
from shared.capabilities.ai.agent.loop import AgentHalt
from shared.capabilities.ai.context_manager import compress_messages, prepare_llm_context


class _FakeLLM:
    def __init__(self, replies: list[dict]) -> None:
        self.replies = list(replies)
        self.calls = 0
        self.seen_messages: list[list[dict]] = []

    async def chat_message(self, messages, temperature=0.7, tools=None, **kwargs):
        del temperature, tools, kwargs
        self.seen_messages.append([dict(m) for m in messages])
        idx = min(self.calls, len(self.replies) - 1)
        self.calls += 1
        return self.replies[idx]


class _FakeStreamLLM(_FakeLLM):
    """带 ``chat_message_stream`` 的假 LLM：按轮次产出事件流。

    ``rounds[i]`` 为第 i 轮的事件列表（reasoning 增量 + 最终 message）；
    轮次耗尽后复用最后一轮。``chat_message`` 仅作回落计数，正常不应被调到。
    """

    def __init__(self, rounds: list[list[dict]]) -> None:
        super().__init__(replies=[{"role": "assistant", "content": "fallback"}])
        self.rounds = rounds

    async def chat_message_stream(self, messages, temperature=0.7, tools=None, **kwargs):
        del messages, temperature, tools, kwargs
        idx = min(self.calls, len(self.rounds) - 1)
        self.calls += 1
        for event in self.rounds[idx]:
            yield event


@pytest.mark.asyncio
async def test_agent_loop_streams_reasoning_and_assembles_rounds() -> None:
    """流式轮次：reasoning 增量实时回调（轮间补分隔），message 事件驱动工具执行。"""
    llm = _FakeStreamLLM(
        rounds=[
            [
                {"type": "reasoning", "text": "先想"},
                {"type": "reasoning", "text": "要查什么"},
                {
                    "type": "message",
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "c1",
                                "type": "function",
                                "function": {"name": "lookup", "arguments": "{}"},
                            }
                        ],
                    },
                },
            ],
            [
                {"type": "reasoning", "text": "汇总观察"},
                {
                    "type": "message",
                    "message": {"role": "assistant", "content": "最终回答。" * 60},
                },
            ],
        ]
    )
    executed: list[str] = []
    seen_thinking: list[str] = []

    async def execute(name: str, args: dict) -> str:
        executed.append(name)
        return "ok"

    result = await run_agent_loop(
        llm,
        [{"role": "user", "content": "hi"}],
        tools=[{"type": "function", "function": {"name": "lookup"}}],
        execute=execute,
        max_rounds=4,
        on_thinking=seen_thinking.append,
    )
    assert executed == ["lookup"]
    # 思考增量实时到达；第二轮首段带轮间分隔
    assert seen_thinking == ["先想", "要查什么", "\n\n汇总观察"]
    # 持久化通道按轮拼接（无展示用分隔前缀）
    assert result.thinking == "先想要查什么\n\n汇总观察"
    assert result.final_content == "最终回答。" * 60
    # 全程走流式，未回落非流式
    assert llm.seen_messages == []


@pytest.mark.asyncio
async def test_agent_loop_falls_back_when_stream_unsupported() -> None:
    """客户端声明不支持流式（NotImplementedError）时回落非流式 chat_message。"""

    class _NoStreamLLM(_FakeLLM):
        async def chat_message_stream(self, *args, **kwargs):
            raise NotImplementedError("responses 协议不支持流式工具轮")
            yield  # pragma: no cover

    llm = _NoStreamLLM([{"role": "assistant", "content": "直接回答。" * 60, "tool_calls": None}])

    async def execute(name: str, args: dict) -> str:
        return "ok"

    result = await run_agent_loop(
        llm,
        [{"role": "user", "content": "hi"}],
        tools=[{"type": "function", "function": {"name": "lookup"}}],
        execute=execute,
        max_rounds=3,
    )
    assert result.final_content == "直接回答。" * 60
    assert llm.calls == 1


@pytest.mark.asyncio
async def test_agent_loop_first_round_content_skips_second_llm() -> None:
    llm = _FakeLLM([{"role": "assistant", "content": "完整回答。" * 60, "tool_calls": None}])
    executed: list[str] = []

    async def execute(name: str, args: dict) -> str:
        executed.append(name)
        return "ok"

    result = await run_agent_loop(
        llm,
        [{"role": "user", "content": "hi"}],
        tools=[{"type": "function", "function": {"name": "web_search"}}],
        execute=execute,
        max_rounds=3,
    )
    assert result.final_content == "完整回答。" * 60
    assert result.tool_used is False
    assert executed == []
    assert llm.calls == 1


@pytest.mark.asyncio
async def test_agent_loop_drift_retry_nudges_short_preamble_once() -> None:
    """opt-in 纠偏：无工具的短行动旁白不作为最终回答，注入一次性提示重试；
    模型坚持同样输出时按最终回答接受（有界，不死循环）。"""
    preamble = "我并行搜一下近期面经，整理高频考点。"
    llm = _FakeLLM([{"role": "assistant", "content": preamble, "tool_calls": None}])
    executed: list[str] = []

    async def execute(name: str, args: dict) -> str:
        executed.append(name)
        return "ok"

    result = await run_agent_loop(
        llm,
        [{"role": "user", "content": "搜索近期面经"}],
        tools=[{"type": "function", "function": {"name": "web_search"}}],
        execute=execute,
        max_rounds=4,
        drift_retry=True,
    )
    assert result.final_content == preamble
    assert executed == []
    assert llm.calls == 2, "短旁白应触发恰好一次纠偏重试"
    # 纠偏提示仅随第二次调用注入，且不持久化进消息序列
    assert "没有调用任何工具" in llm.seen_messages[1][-1]["content"]
    assert llm.seen_messages[0][-1].get("content") == "搜索近期面经"
    assert not any(
        "没有调用任何工具" in str(m.get("content")) for m in result.messages
    )


@pytest.mark.asyncio
async def test_agent_loop_drift_retry_skips_after_tools_used() -> None:
    """用过工具后的短收尾正文是合法最终回答，不触发纠偏。"""
    llm = _FakeLLM(
        [
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {"id": "c1", "function": {"name": "lookup", "arguments": "{}"}}
                ],
            },
            {"role": "assistant", "content": "综合结果", "tool_calls": None},
        ]
    )

    async def execute(name: str, args: dict) -> str:
        return "ok"

    result = await run_agent_loop(
        llm,
        [{"role": "user", "content": "hi"}],
        tools=[{"type": "function", "function": {"name": "lookup"}}],
        execute=execute,
        max_rounds=4,
        drift_retry=True,
    )
    assert result.final_content == "综合结果"
    assert llm.calls == 2


@pytest.mark.asyncio
async def test_agent_loop_drift_retry_off_by_default() -> None:
    """未开启 drift_retry 时保持原语义：短正文即时收尾，不额外调用。"""
    llm = _FakeLLM([{"role": "assistant", "content": "我去搜一下。", "tool_calls": None}])

    async def execute(name: str, args: dict) -> str:
        return "ok"

    await run_agent_loop(
        llm,
        [{"role": "user", "content": "hi"}],
        tools=[{"type": "function", "function": {"name": "web_search"}}],
        execute=execute,
        max_rounds=3,
    )
    assert llm.calls == 1


@pytest.mark.asyncio
async def test_agent_loop_forwards_reasoning_to_callback() -> None:
    """message 携带 reasoning 时逐轮回调 on_thinking，并汇总进 LoopResult.thinking。"""
    llm = _FakeLLM(
        [
            {
                "role": "assistant",
                "content": None,
                "reasoning": "先想一下要查什么",
                "tool_calls": [
                    {"id": "c1", "function": {"name": "lookup", "arguments": "{}"}}
                ],
            },
            {
                "role": "assistant",
                "content": "最终回答。" * 60,
                "reasoning": "组织答案结构",
                "tool_calls": None,
            },
        ]
    )

    async def execute(name: str, args: dict) -> str:
        return "ok"

    seen: list[str] = []
    result = await run_agent_loop(
        llm,
        [{"role": "user", "content": "hi"}],
        tools=[{"type": "function", "function": {"name": "lookup"}}],
        execute=execute,
        max_rounds=3,
        on_thinking=seen.append,
    )
    assert seen == ["先想一下要查什么", "\n\n组织答案结构"], (
        "展示通道第二轮首段应带轮间分隔"
    )
    assert result.thinking == "先想一下要查什么\n\n组织答案结构"
    # reasoning 仅回传展示，不得写入消息序列
    assert all("reasoning" not in m for m in result.messages)


@pytest.mark.asyncio
async def test_agent_loop_content_after_tools_is_final() -> None:
    """模型用过工具后返回正文：该正文即最终回答，不做无工具的二次生成。"""
    llm = _FakeLLM(
        [
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "c1",
                        "function": {"name": "lookup", "arguments": '{"q":"x"}'},
                    }
                ],
            },
            {"role": "assistant", "content": "综合结果", "tool_calls": None},
        ]
    )

    async def execute(name: str, args: dict) -> str:
        assert name == "lookup"
        assert args.get("q") == "x"
        return "hit"

    result = await run_agent_loop(
        llm,
        [{"role": "user", "content": "查一下"}],
        tools=[{"type": "function", "function": {"name": "lookup"}}],
        execute=execute,
        max_rounds=3,
    )
    assert result.tool_used is True
    assert result.final_content == "综合结果"
    tool_msgs = [m for m in result.messages if m.get("role") == "tool"]
    assert tool_msgs and "hit" in tool_msgs[0]["content"]
    # 恰好两次 LLM 调用（工具轮 + 收尾轮），没有额外生成
    assert llm.calls == 2


def test_working_memory_roundtrip_via_messages() -> None:
    mem = WorkingMemory()
    mem.remember("weak", "没讲清 QPS")
    mem.remember("asked", "缓存淘汰策略")
    msgs = prepare_llm_context(
        [{"role": "system", "content": "规则"}, {"role": "user", "content": "你好"}],
        max_tokens=0,
        memory=mem,
    )
    loaded = WorkingMemory.load_from_messages(msgs)
    assert "没讲清 QPS" in loaded.weak_points
    assert loaded.asked


def test_compress_digest_includes_omitted_user_text() -> None:
    msgs = (
        [{"role": "system", "content": "规则"}]
        + [{"role": "user", "content": f"old-topic-{i}"} for i in range(30)]
        + [{"role": "user", "content": "new-topic"}]
    )
    mem = WorkingMemory()
    out = compress_messages(msgs, max_tokens=80, memory=mem)
    summary = [m for m in out if m["role"] == "system" and "上下文压缩" in m["content"]]
    assert summary
    assert "old-topic-0" in summary[0]["content"]
    assert mem.notes


@pytest.mark.asyncio
async def test_agent_halt_appends_observation_and_stops() -> None:
    llm = _FakeLLM(
        [
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {"id": "c1", "function": {"name": "ask_user", "arguments": "{}"}}
                ],
            },
            {"role": "assistant", "content": "不应到达", "tool_calls": None},
        ]
    )

    async def execute(name: str, args: dict) -> str:
        raise AgentHalt("已向用户提问")

    result = await run_agent_loop(
        llm,
        [{"role": "user", "content": "hi"}],
        tools=[{"type": "function", "function": {"name": "ask_user"}}],
        execute=execute,
        max_rounds=3,
    )
    assert result.halted is True
    assert result.final_content is None
    tool_msgs = [m for m in result.messages if m.get("role") == "tool"]
    assert tool_msgs and "已向用户提问" in tool_msgs[0]["content"]
    # halt 后不再进下一轮 LLM
    assert llm.calls == 1


@pytest.mark.asyncio
async def test_parallel_tools_keep_pairing() -> None:
    llm = _FakeLLM(
        [
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {"id": "c1", "function": {"name": "slow", "arguments": "{}"}},
                    {"id": "c2", "function": {"name": "fast", "arguments": "{}"}},
                ],
            },
            {"role": "assistant", "content": "done", "tool_calls": None},
        ]
    )

    async def execute(name: str, args: dict) -> str:
        if name == "slow":
            await asyncio.sleep(0.05)
            return "slow-result"
        return "fast-result"

    result = await run_agent_loop(
        llm,
        [{"role": "user", "content": "hi"}],
        tools=[
            {"type": "function", "function": {"name": "slow"}},
            {"type": "function", "function": {"name": "fast"}},
        ],
        execute=execute,
        max_rounds=2,
    )
    tool_msgs = [m for m in result.messages if m.get("role") == "tool"]
    assert [m["tool_call_id"] for m in tool_msgs] == ["c1", "c2"]
    assert "slow-result" in tool_msgs[0]["content"]
    assert "fast-result" in tool_msgs[1]["content"]
    # 工具后的模型正文直接作为最终回答返回
    assert result.final_content == "done"


@pytest.mark.asyncio
async def test_agent_loop_last_round_injects_wrap_up_hint() -> None:
    """最后一轮注入收尾提示(仅本次调用可见),且不写入持久消息序列。"""
    llm = _FakeLLM(
        [
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {"id": "c1", "function": {"name": "lookup", "arguments": "{}"}}
                ],
            },
            {"role": "assistant", "content": "收尾回答", "tool_calls": None},
        ]
    )

    async def execute(name: str, args: dict) -> str:
        return "ok"

    result = await run_agent_loop(
        llm,
        [{"role": "user", "content": "hi"}],
        tools=[{"type": "function", "function": {"name": "lookup"}}],
        execute=execute,
        max_rounds=2,
    )
    # 首轮无提示;末轮(最后一轮工具机会)带收尾提示
    assert llm.seen_messages[0][-1]["role"] != "system"
    hint = llm.seen_messages[1][-1]
    assert hint["role"] == "system" and "最后一轮" in hint["content"]
    assert result.final_content == "收尾回答"
    assert not any(
        m.get("role") == "system" and "最后一轮" in str(m.get("content"))
        for m in result.messages
    ), "收尾提示不得持久化进消息序列"


@pytest.mark.asyncio
async def test_agent_loop_no_hint_when_first_round() -> None:
    """仅一轮可用时不注入提示(没有「预算将尽」语义)。"""
    llm = _FakeLLM([{"role": "assistant", "content": "直接回答", "tool_calls": None}])

    async def execute(name: str, args: dict) -> str:
        return "ok"

    await run_agent_loop(
        llm,
        [{"role": "user", "content": "hi"}],
        tools=[{"type": "function", "function": {"name": "lookup"}}],
        execute=execute,
        max_rounds=1,
    )
    assert all(
        not (m.get("role") == "system" and "最后一轮" in str(m.get("content")))
        for call in llm.seen_messages
        for m in call
    )

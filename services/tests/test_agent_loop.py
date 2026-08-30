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

    async def chat_message(self, messages, temperature=0.7, tools=None, **kwargs):
        del messages, temperature, tools, kwargs
        idx = min(self.calls, len(self.replies) - 1)
        self.calls += 1
        return self.replies[idx]


@pytest.mark.asyncio
async def test_agent_loop_first_round_content_skips_second_llm() -> None:
    llm = _FakeLLM([{"role": "assistant", "content": "直接回答", "tool_calls": None}])
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
    assert result.final_content == "直接回答"
    assert result.tool_used is False
    assert executed == []
    assert llm.calls == 1


@pytest.mark.asyncio
async def test_agent_loop_runs_tool_then_stops_for_stream() -> None:
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
    assert result.final_content is None
    tool_msgs = [m for m in result.messages if m.get("role") == "tool"]
    assert tool_msgs and "hit" in tool_msgs[0]["content"]


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
    # 已调用过工具:final_content 为 None,由调用方流式生成最终回答
    assert result.final_content is None

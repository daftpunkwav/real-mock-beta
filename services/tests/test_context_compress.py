"""上下文压缩单元测试。"""

from __future__ import annotations

import pytest

from shared.capabilities.ai.agent.working_memory import WorkingMemory
from shared.capabilities.ai.context_manager import (
    compact_with_summary,
    compress_messages,
    estimate_messages_tokens,
    estimate_tokens,
)


def test_estimate_tokens_empty() -> None:
    assert estimate_tokens("") == 0


def test_estimate_tokens_rough_ratio() -> None:
    # 1.5 字符/token 启发式
    assert estimate_tokens("abc") == 2  # 3 / 1.5 = 2
    assert estimate_tokens("你好") == 1  # 2 / 1.5 = 1


def test_compress_under_threshold_returns_input() -> None:
    msgs = [{"role": "user", "content": "短消息"}]
    out = compress_messages(msgs, max_tokens=10000)
    assert out is msgs or out == msgs


def test_compress_keeps_all_system_messages() -> None:
    msgs = [
        {"role": "system", "content": "规则一"},
        {"role": "system", "content": "规则二"},
    ] + [{"role": "user", "content": f"消息{i}"} for i in range(50)]
    out = compress_messages(msgs, max_tokens=100)
    system = [m for m in out if m["role"] == "system"]
    # 包含 2 条原始 system 消息 + 1 条压缩说明
    rule_msgs = [m for m in system if m["content"] in ("规则一", "规则二")]
    assert len(rule_msgs) == 2
    # 最近 20 条对话应保留
    assert any("消息49" in m["content"] for m in out)


def test_compress_adds_summary_marker() -> None:
    msgs = (
        [{"role": "system", "content": "规则"}]
        + [{"role": "user", "content": f"old{i}"} for i in range(30)]
        + [{"role": "user", "content": f"new{i}"} for i in range(5)]
    )
    out = compress_messages(msgs, max_tokens=100)
    summary = [m for m in out if m["role"] == "system" and "上下文压缩" in m["content"]]
    assert summary


def test_estimate_messages_tokens_sums_contents() -> None:
    msgs = [
        {"role": "system", "content": "abc"},
        {"role": "user", "content": "defg"},
    ]
    # 3/1.5=2, 4/1.5=2 -> 4
    assert estimate_messages_tokens(msgs) == 4


def test_compress_triggers_at_30_percent_threshold() -> None:
    """触发阈值已从 60% 降到 30%，即使 messages 总 token < max_tokens*0.6 也会被压缩。"""
    # 构造每个 user 消息约 30 token，共 5 条 → 150 tokens
    big = "内容内容内容内容内容内容内容内容" * 5  # 中文 8*5=40 chars = ~27 token
    msgs = [{"role": "user", "content": big + str(i)} for i in range(5)]
    total = sum(estimate_messages_tokens([m]) for m in msgs)
    # 设定 max_tokens 让比例落在 (30%, 60%) 区间内:
    # 30% * max_tokens < total < 60% * max_tokens
    max_tokens = int(total / 0.45)  # ~恰在 45% 占比
    out = compress_messages(msgs, max_tokens=max_tokens)
    # 原本 5 条 user 消息，压缩后应当 < 5 条,且加入 system 摘要
    system_marker = [m for m in out if m["role"] == "system" and "上下文压缩" in m["content"]]
    assert system_marker, "30% 阈值下也应触发压缩"


def test_estimate_messages_tokens_handles_list_content() -> None:
    """多模态 content 为 list[str,...] 时也正确累加。"""
    msgs = [
        {"role": "user", "content": [{"type": "text", "text": "hello world"}]},
        {"role": "user", "content": "短"},
    ]
    # "hello world" 11 chars => ~7 token; "短" 1 char => 1 token => 总约 8
    assert estimate_messages_tokens(msgs) >= 5


def test_estimate_messages_tokens_skips_empty_content() -> None:
    msgs = [
        {"role": "user", "content": ""},
        {"role": "assistant", "content": None},
    ]
    # 空 / None content 不应抛异常
    total = estimate_messages_tokens(msgs)
    assert total >= 0

# ── 旧工具对折叠 ────────────────────────────────────────────────


def _turn_with_tools(user_text: str, tool_result: str, answer: str) -> list[dict]:
    """构造一轮「用户 → 工具调用 → 工具结果 → 回答」的消息。"""
    return [
        {"role": "user", "content": user_text},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {"id": "c1", "type": "function", "function": {"name": "web_search", "arguments": "{}"}}
            ],
        },
        {"role": "tool", "tool_call_id": "c1", "content": tool_result},
        {"role": "assistant", "content": answer},
    ]


def test_compress_prunes_stale_tool_pairs() -> None:
    """最近用户消息之前的工具调用对应被折叠,最后一轮保持配对完整。"""
    big = "观察" * 2000  # 单条工具结果很大
    msgs = (
        [{"role": "system", "content": "规则"}]
        + _turn_with_tools("旧问题", big, "旧回答" + "补" * 1000)
        + [{"role": "user", "content": "最新问题"}]
    )
    out = compress_messages(msgs, max_tokens=10000)  # 触发阈值但不产生省略
    roles = [m["role"] for m in out]
    assert "tool" not in roles, "旧工具结果应被折叠"
    assert not any(m.get("tool_calls") for m in out), "旧 tool_calls 结构应被移除"
    assert any(m["role"] == "assistant" and m.get("content", "").startswith("旧回答") for m in out)
    # 最新一轮(当前工具对)如果在场必须原样保留——此处最后是 user,不涉及


def test_compress_keeps_current_turn_tool_pairs() -> None:
    """当前轮(最后一条 user 之后)的 tool_calls/tool 配对不可破坏。"""
    big = "内容" * 3000
    msgs = (
        [{"role": "system", "content": "规则"}]
        + [{"role": "user", "content": "旧问题" + big}]
        + [{"role": "assistant", "content": "旧回答" + big}]
        + _turn_with_tools("最新问题", "工具结果", "最新回答")
    )
    out = compress_messages(msgs, max_tokens=500, keep_recent=20)
    tail_user = max(i for i, m in enumerate(out) if m["role"] == "user")
    current = out[tail_user:]
    assert any(m.get("role") == "tool" for m in current), "当前轮 tool 结果必须保留"
    assert any(m.get("tool_calls") for m in current), "当前轮 tool_calls 必须保留"


# ── LLM 纪要式压缩 ──────────────────────────────────────────────


class _SummarizerLLM:
    """可编程的压缩用 LLM:chat 返回固定纪要,或抛错;记录调用。"""

    def __init__(self, reply: str = "", error: Exception | None = None):
        self.reply = reply
        self.error = error
        self.chat_calls: list[list[dict]] = []

    async def chat(self, messages, temperature=0.7, **kwargs):
        del temperature, kwargs
        self.chat_calls.append(messages)
        if self.error is not None:
            raise self.error
        return self.reply


def _big_history(turns: int = 12) -> list[dict]:
    msgs: list[dict] = [{"role": "system", "content": "规则"}]
    for i in range(turns):
        msgs.append({"role": "user", "content": f"问题{i}：" + "背景" * 300})
        msgs.append({"role": "assistant", "content": f"回答{i}：" + "结论" * 300})
    return msgs


@pytest.mark.asyncio
async def test_compact_with_summary_under_threshold_skips_llm() -> None:
    llm = _SummarizerLLM(reply="纪要")
    msgs = [{"role": "user", "content": "短问题"}]
    out = await compact_with_summary(msgs, 100000, llm=llm)
    assert out == msgs
    assert llm.chat_calls == []


@pytest.mark.asyncio
async def test_compact_with_summary_generates_structured_summary() -> None:
    llm = _SummarizerLLM(reply="会话目标：分析简历\n待办：模拟追问")
    mem = WorkingMemory()
    out = await compact_with_summary(_big_history(), 500, memory=mem, llm=llm, keep_recent=4)
    summaries = [
        m for m in out
        if m["role"] == "system" and str(m.get("content", "")).startswith("[会话纪要]")
    ]
    assert len(summaries) == 1
    assert "会话目标" in summaries[0]["content"]
    # 被省略的早期对话不再以原样存在;最近窗口保留
    assert not any(m["role"] == "user" and str(m.get("content", "")).startswith("问题0") for m in out)
    assert any(m["role"] == "user" and str(m.get("content", "")).startswith("问题11") for m in out)
    assert mem.notes, "被省略对话应同时吸收进工作记忆"
    assert llm.chat_calls, "超阈值时必须调用 LLM 生成纪要"


@pytest.mark.asyncio
async def test_compact_with_summary_falls_back_to_digest_on_llm_failure() -> None:
    llm = _SummarizerLLM(error=RuntimeError("llm down"))
    out = await compact_with_summary(_big_history(), 500, llm=llm, keep_recent=4)
    digests = [
        m for m in out
        if m["role"] == "system" and str(m.get("content", "")).startswith("[上下文压缩]")
    ]
    assert digests, "LLM 失败必须回退规则摘要"


@pytest.mark.asyncio
async def test_compact_with_summary_supersedes_previous_summary() -> None:
    old = _big_history()
    old.insert(1, {"role": "system", "content": "[会话纪要] 旧纪要内容"})
    llm = _SummarizerLLM(reply="新纪要")
    out = await compact_with_summary(old, 500, llm=llm, keep_recent=4)
    summaries = [
        m for m in out
        if m["role"] == "system" and str(m.get("content", "")).startswith("[会话纪要]")
    ]
    assert len(summaries) == 1
    assert "旧纪要内容" not in summaries[0]["content"]
    # 上一份纪要应作为增量更新输入传给 LLM
    prompt = llm.chat_calls[0][0]["content"]
    assert "旧纪要内容" in prompt

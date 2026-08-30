"""LLM 流式净化器:特殊 token 剥离与 reasoning 包裹。"""

from __future__ import annotations

import pytest

from shared.capabilities.ai.llm.stream_filters import (
    SpecialTokenFilter,
    StreamSanitizer,
    sanitize_special_tokens,
)


def _feed_all(chunks: list[str]) -> str:
    f = SpecialTokenFilter()
    return "".join(f.feed(c) for c in chunks) + f.flush()


def test_single_chunk_minimax_leak_stripped() -> None:
    out = _feed_all(["。|<|minimax|>|<|tool_call|> 正文开始"])
    assert out == "。 正文开始"


def test_cross_chunk_split_stripped() -> None:
    out = _feed_all(["<|mini", "max|>|<|tool", "_call|>hi"])
    assert out == "hi"


def test_angle_bracket_close_form_stripped() -> None:
    # MiniMax 泄漏的第二种闭合形态 <|body>|（body 后直接 >|）
    out = _feed_all(["<|Agent 可观测", "性 trace 面试题>|后续正文"])
    assert out == "后续正文"


def test_screenshot3_full_leak_stripped() -> None:
    text = (
        "。|<|minimax|>|<|tool_call|> |<|minimax|>|<|Agent 可观测性 trace 成本归因 "
        "在线评估 面试题>|<|minimax|>|<|minimax|>|<|Agent 评测 实习生 字节 阿里 腾讯 "
        "面试流程 2026>|<|minimax|>|<|minimax|>| |<|minimax|>"
    )
    out = _feed_all([text])
    assert "<|" not in out
    assert "|>" not in out


def test_plain_text_with_unclosed_bracket_kept() -> None:
    out = _feed_all(["a <| b 代码示例"])
    assert out == "a <| b 代码示例"


def test_space_body_kept() -> None:
    # "<| b >" 是正文不是 token（body 首字符为空白）
    out = _feed_all(["a <| b > c 保留"])
    assert out == "a <| b > c 保留"


def test_overlong_body_kept() -> None:
    long_body = "x" * 80
    out = _feed_all([f"<|{long_body}|>"])
    assert out == f"<|{long_body}|>"


def test_markdown_table_pipe_kept() -> None:
    table = "| 列1 | 列2 |\n| --- | --- |\n| a | b |"
    out = _feed_all([table])
    assert out == table


def test_leading_pipe_held_then_released() -> None:
    # "|" 被暂扣后,若不构成 token 必须原样放行
    out = _feed_all(["abc|def"])
    assert out == "abc|def"


def test_stream_sanitizer_reasoning_wrap() -> None:
    s = StreamSanitizer()
    r = s.feed_reasoning("推理中") + s.feed_content("正式<|minimax|>") + s.flush()
    assert r == "<think>推理中</think>正式"


def test_stream_sanitizer_reasoning_only() -> None:
    s = StreamSanitizer()
    r = s.feed_reasoning("只有思考") + s.flush()
    assert r == "<think>只有思考</think>"


def test_bracket_form_separator_leak_stripped() -> None:
    # MiniMax 反转变体:]<]minimax[>[ 分隔单元(实测泄漏形态)
    text = (
        "更难答对:]<]minimax[>[<tool_call>\n]<]minimax[>[<invoke name=\"quiz\">"
        "]<]minimax[>[<question>请解释 Function Calling 流程。</question>"
        "]<]minimax[>[</question>]<]minimax[>[<type>open]<]minimax[>[</type>"
        "]<]minimax[>[</invoke>\n]<]minimax[>[</tool_call>"
    )
    s = StreamSanitizer()
    r = s.feed_content(text) + s.flush()
    assert "minimax" not in r
    assert "<tool_call>" not in r
    assert "<invoke" not in r
    # quiz 题目被转换为可读正文,而不是一起丢失
    assert "请解释 Function Calling 流程。" in r
    assert "练习题" in r


def test_inline_tool_call_block_cross_chunk() -> None:
    s = StreamSanitizer()
    chunks = ["前文<tool_call><invoke name=", "\"quiz\"><question>题干", "</question></invoke></tool_call>后文"]
    r = "".join(s.feed_content(c) for c in chunks) + s.flush()
    assert "<tool_call>" not in r and "<invoke" not in r
    assert "前文" in r and "后文" in r
    assert "题干" in r


def test_inline_xml_without_question_dropped() -> None:
    s = StreamSanitizer()
    r = s.feed_content("正文<tool_call><invoke name=\"x\"><arg>1</arg></invoke></tool_call>继续") + s.flush()
    assert r == "正文继续"


def test_normal_xml_content_kept() -> None:
    # 正文合法讨论 XML 标签(非 tool_call 块)不受影响
    text = "配置里用 <question> 标签需要转义,示例 `<invoke>`。"
    s = StreamSanitizer()
    r = s.feed_content(text) + s.flush()
    assert r == text


def test_sanitize_special_tokens_one_shot() -> None:
    assert sanitize_special_tokens("。|<|minimax|>|<|tool_call|> X") == "。 X"
    assert sanitize_special_tokens("正常文本") == "正常文本"


@pytest.mark.parametrize(
    "chunks,expected",
    [
        (["<|a|>", "<|b|>", "<|c|>"], ""),
        (["<|", "a|>", "text"], "text"),
        (["正文<|", "tail"], "正文<|tail"),
    ],
)
def test_parametrized_chunks(chunks: list[str], expected: str) -> None:
    assert _feed_all(chunks) == expected

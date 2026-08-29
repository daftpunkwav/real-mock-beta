"""say-first 流式解析器与回合输出语义解析的单元测试。"""

from __future__ import annotations

import json

from shared.capabilities.ai.llm.say_first_stream import SayFirstStreamParser
from interview_service.services.interview.turn_output import parse_turn_output


def feed_all(parser: SayFirstStreamParser, text: str, chunk: int) -> str:
    """按指定块大小切分喂入，返回累计明文（含 finish 残余）。"""
    out: list[str] = []
    for i in range(0, len(text), chunk):
        out.append(parser.feed(text[i : i + chunk]))
    out.append(parser.finish())
    return "".join(out)


FULL = json.dumps(
    {
        "say": "好，我们聊聊秒杀系统。先说说架构分层？",
        "v": 1,
        "wait_seconds": 90,
        "emotion": "serious",
        "phase_complete": False,
        "interview_complete": False,
        "turn_score": {"brief": "提到了中间件", "rating": 3, "weak_points": ["一致性"]},
        "probe": "从接入层想想",
        "sources": ["resume"],
    },
    ensure_ascii=False,
)


def test_say_streams_incrementally_and_controls_parse() -> None:
    for chunk in (1, 3, 7, 10000):  # 覆盖最坏跨 token 切分
        parser = SayFirstStreamParser()
        text = feed_all(parser, FULL, chunk)
        assert text == "好，我们聊聊秒杀系统。先说说架构分层？", f"chunk={chunk}"
        assert not parser.degraded
        controls = parser.controls
        assert controls and controls["wait_seconds"] == 90
        assert controls["turn_score"]["rating"] == 3


def test_escapes_and_cn_quotes() -> None:
    body = '{"say": "引号\\"与\\\\反斜杠与\\n换行与“中文引号”", "wait_seconds": 30}'
    parser = SayFirstStreamParser()
    text = feed_all(parser, body, 4)
    assert text == '引号"与\\反斜杠与\n换行与“中文引号”'
    assert parser.controls and parser.controls["wait_seconds"] == 30


def test_unicode_escape_across_tokens() -> None:
    body = '{"say": "A\\u4f60\\u597dB", "wait_seconds": 5}'
    parser = SayFirstStreamParser()
    text = feed_all(parser, body, 2)
    assert text == "A你好B"


def test_unclosed_say_falls_back_to_tail() -> None:
    body = '{"say": "说到一半就断了'
    parser = SayFirstStreamParser()
    text = feed_all(parser, body, 5)
    assert text == "说到一半就断了"
    assert parser.controls is None


def test_plain_text_degrades_with_full_raw() -> None:
    body = "这是一个纯文本回复，没有任何 JSON 结构。"
    parser = SayFirstStreamParser()
    text = feed_all(parser, body, 6)
    assert text == body
    assert parser.degraded
    assert parser.raw_text == body
    assert parser.controls is None


def test_late_say_key_still_extracts() -> None:
    """键序漂移（say 不在最前）仍提取 say；之前的内容被丢弃不进语音。"""
    body = '{"wait_seconds": 9, "say": "你说得不错", "emotion": "smile"}'
    parser = SayFirstStreamParser()
    text = feed_all(parser, body, 3)
    assert text == "你说得不错"
    assert parser.controls and parser.controls["emotion"] == "smile"


def test_non_string_say_degrades_to_raw() -> None:
    body = '{"say": 42, "wait_seconds": 1}'
    parser = SayFirstStreamParser()
    text = feed_all(parser, body, 4)
    # 流式提取放弃，finish 回捞整体 parse 的 say 文本形态
    assert parser.controls is not None
    degraded_or_text = parser.degraded or text == ""
    assert degraded_or_text or text == "42"


def test_parse_turn_output_full() -> None:
    controls = json.loads(FULL)
    out = parse_turn_output(controls, say_text="好，我们聊聊秒杀系统。先说说架构分层？")
    assert out.say.startswith("好，我们聊聊秒杀系统")
    assert out.protocol_version == 1
    assert out.wait_seconds == 90
    assert out.emotion == "serious"
    assert out.phase_complete is False
    assert out.interview_complete is False
    assert out.turn_score is not None
    assert out.turn_score.rating == 3
    assert out.turn_score.weak_points == ("一致性",)
    assert out.probe == "从接入层想想"
    assert out.sources == ("resume",)
    assert out.degraded is False


def test_parse_turn_output_defaults_on_missing() -> None:
    out = parse_turn_output({}, say_text="只有语音")
    assert out.wait_seconds == 0
    assert out.emotion == "neutral"
    assert out.turn_score is None
    assert out.probe is None
    assert out.sources == ()
    assert out.degraded is False


def test_parse_turn_output_none_controls_degrades() -> None:
    out = parse_turn_output(None, say_text="纯文本", degraded=True)
    assert out.degraded is True
    assert out.say == "纯文本"
    assert out.wait_seconds == 0


def test_parse_turn_output_type_drift_is_safe() -> None:
    out = parse_turn_output(
        {
            "say": "x",
            "v": "1",
            "wait_seconds": "abc",
            "emotion": "angry!!!",
            "phase_complete": "yes",
            "interview_complete": None,
            "turn_score": "低分",
            "probe": 123,
            "sources": "resume",
        },
        say_text="x",
    )
    assert out.wait_seconds == 0
    assert out.emotion == "neutral"
    assert out.phase_complete is False
    assert out.interview_complete is False
    assert out.turn_score is None
    assert out.probe == "123"  # 非空标量容忍为文本
    assert out.sources == ()


def test_wait_seconds_clamped() -> None:
    assert parse_turn_output({"wait_seconds": -5}, say_text="s").wait_seconds == 0
    assert parse_turn_output({"wait_seconds": 9999}, say_text="s").wait_seconds == 120


def test_turn_score_partial_and_empty() -> None:
    assert parse_turn_output({"turn_score": None}, say_text="s").turn_score is None
    out = parse_turn_output({"turn_score": {"brief": ""}}, say_text="s")
    assert out.turn_score is None  # 全空 → None
    out2 = parse_turn_output(
        {"turn_score": {"brief": "不错", "rating": 9, "weak_points": ["a", "b", "c"]}},
        say_text="s",
    )
    assert out2.turn_score is not None
    assert out2.turn_score.rating == 5  # 钳位
    assert len(out2.turn_score.weak_points) == 2  # 截断到 2 条

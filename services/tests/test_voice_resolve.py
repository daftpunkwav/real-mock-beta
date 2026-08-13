"""TTS 音色解析、切句与韵律单元测试。

手动验证清单（联调时勾选）：
1. 专业男 / 严厉专家 / 温和女各开一场：音色分别接近云扬 / 云健 / 晓晓
2. 温和 vs 压迫人设：语速可感知差异
3. 含 [emotion:smile] 等标记：合成 rate/pitch 有变化，Avatar 表情同步
4. WebGL 失败时 CSS 人像口型跟电平，无随机乱抖
5. TTS 失败仍有文字；tts_playback_done 握手正常开麦
"""

from __future__ import annotations

from shared.capabilities.voice.tts.edge import (
    extract_emotion,
    should_flush_sentence_buffer,
    split_sentences,
)
from shared.capabilities.voice.tts.voice_resolve import (
    resolve_prosody,
    resolve_session_voice,
    with_emotion,
)


def test_avatar_voice_priority_over_settings():
    assert (
        resolve_session_voice("professional_male", "zh-CN-XiaoxiaoNeural")
        == "zh-CN-YunyangNeural"
    )
    assert (
        resolve_session_voice("gentle_female", "zh-CN-YunyangNeural")
        == "zh-CN-XiaoxiaoNeural"
    )
    assert (
        resolve_session_voice("strict_expert", None) == "zh-CN-YunjianNeural"
    )


def test_fallback_to_settings_then_default():
    assert (
        resolve_session_voice("unknown_avatar", "zh-CN-YunxiNeural")
        == "zh-CN-YunxiNeural"
    )
    assert resolve_session_voice(None, None) == "zh-CN-XiaoxiaoNeural"


def test_personality_prosody_differs():
    gentle = resolve_prosody(
        avatar_id="gentle_female",
        personality="gentle",
        strictness=2,
    )
    pressure = resolve_prosody(
        avatar_id="professional_male",
        personality="pressure",
        strictness=8,
    )
    assert gentle.voice == "zh-CN-XiaoxiaoNeural"
    assert pressure.voice == "zh-CN-YunyangNeural"
    # 温和应更慢（负向 %），压迫应更快
    assert int(gentle.rate.replace("%", "")) < 0
    assert int(pressure.rate.replace("%", "")) > 0


def test_emotion_overlay():
    base = resolve_prosody(
        avatar_id="professional_male",
        personality="professional",
        emotion=None,
    )
    smile = with_emotion(base, "smile")
    serious = with_emotion(base, "serious")
    assert int(smile.pitch.replace("Hz", "")) > int(base.pitch.replace("Hz", "") or "0")
    assert int(serious.rate.replace("%", "")) < int(base.rate.replace("%", "") or "0")


def test_split_sentences_includes_semicolon_ellipsis():
    parts = split_sentences("第一句。第二句；第三句…第四句！")
    assert len(parts) >= 3
    assert any("第一句" in p for p in parts)


def test_soft_flush_on_comma_after_min_chars():
    short = "你好，世界"
    assert not should_flush_sentence_buffer(short)
    long = ("测" * 17) + "，"
    assert should_flush_sentence_buffer(long, soft_min=14)
    assert should_flush_sentence_buffer("说完了。")
    assert should_flush_sentence_buffer("好的；")
    assert should_flush_sentence_buffer("字" * 48)


def test_plain_text_strips_markdown_stars():
    from shared.capabilities.voice.tts.edge import _plain_text_for_tts

    assert _plain_text_for_tts("请确认 **GitHub** 用户名") == "请确认 GitHub 用户名"
    assert "*" not in _plain_text_for_tts("这是*斜体*与**粗体**")
    assert "星" not in _plain_text_for_tts("正常文本")


def test_extract_emotion_from_marker():
    assert extract_emotion("很好。[emotion:smile]继续") == "smile"
    assert extract_emotion("没有标记") == "neutral"

"""阶段 3 播报处理者目录。"""

from __future__ import annotations

from typing import Any

from .catalog_schema import _p

# 播报处理者（阶段 3）
SPEAK_PROVIDERS: list[dict[str, Any]] = [
    _p(
        id="custom",
        label="自定义供应商",
        can_speech_speak=True,
        speak_via="tts_from_text",
        default_model="",
        default_api_base="",
        hint="填写 Base URL、API 格式、API Key 与模型名称",
    ),
    _p(
        id="mimo_audio",
        label="小米 MiMo（mimo-v2.5-tts）",
        can_speech_speak=True,
        speak_via="tts_from_text",
        default_model="mimo-v2.5-tts",
        default_api_base="https://token-plan-cn.xiaomimimo.com/v1",
        hint="OpenAI 兼容 chat.completions；通过 audio.voice 指定音色",
    ),
    _p(
        id="edge",
        label="Edge TTS（免费）",
        can_speech_speak=True,
        speak_via="tts_from_text",
        default_model="zh-CN-XiaoxiaoNeural",
        hint="当前默认播报处理者",
    ),
    _p(
        id="minimax_speech",
        label="MiniMax Speech（TTS）",
        can_speech_speak=True,
        speak_via="tts_from_text",
        default_model="speech-2.8-hd",
        default_api_base="https://api.minimaxi.com/v1",
        hint="T2A 文本转语音；可单独配置 TTS Key",
    ),
    _p(
        id="none",
        label="仅字幕（不播报）",
        can_speech_speak=False,
        speak_via="none",
    ),
    _p(
        id="zhipu_glm4_voice",
        label="智谱 GLM-4-Voice（原生出声）",
        can_speech_recognize=True,
        can_interview_reason=True,
        can_speech_speak=True,
        recognize_via="native_audio",
        speak_via="native_audio",
        status="coming_soon",
    ),
    _p(
        id="doubao_s2s",
        label="豆包端到端实时语音（原生出声）",
        can_speech_recognize=True,
        can_speech_speak=True,
        recognize_via="native_audio",
        speak_via="native_audio",
        status="coming_soon",
    ),
]

"""TTS 音色静态数据（语音能力层自持，避免 shared → interview 反向依赖）。

AVATARS / TTS_VOICES 原本在 ``shared.core.options_data``，但 TTS 的
``voice_resolve`` 需要它们；options_data 其余部分（面试选项）归属面试域。
拆分后本模块随 ``services/tts`` 一起属于共享语音能力层。
"""

from __future__ import annotations

AVATARS = [
    {"id": "professional_male", "name": "专业男面试官", "voice": "zh-CN-YunyangNeural"},
    {"id": "senior_male", "name": "资深男面试官", "voice": "zh-CN-YunjianNeural"},
    {"id": "strict_expert", "name": "严厉技术专家", "voice": "zh-CN-YunjianNeural"},
    {"id": "gentle_female", "name": "温和女面试官", "voice": "zh-CN-XiaoxiaoNeural"},
    {"id": "hr_female", "name": "HR 女面试官", "voice": "zh-CN-XiaoyiNeural"},
    {"id": "young_female", "name": "青年女面试官", "voice": "zh-CN-XiaoxiaoNeural"},
]

TTS_VOICES = [
    {"id": "zh-CN-XiaoxiaoNeural", "name": "晓晓（女声）"},
    {"id": "zh-CN-YunxiNeural", "name": "云希（男声）"},
    {"id": "zh-CN-YunyangNeural", "name": "云扬（男声专业）"},
    {"id": "zh-CN-XiaoyiNeural", "name": "晓伊（女声活泼）"},
    {"id": "zh-CN-YunjianNeural", "name": "云健（男声沉稳）"},
]

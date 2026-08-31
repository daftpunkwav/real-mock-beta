"""语音目录的表结构：类型别名与供应商工厂 ``_p``。

拆自 :mod:`...config.catalog`；三张 provider 表与主文件从本模块取 ``_p``。
"""

from __future__ import annotations

from typing import Any, Literal

RecognizeVia = Literal["native_audio", "transcribe_only", "none"]
SpeakVia = Literal["native_audio", "tts_from_text", "none"]
ProviderStatus = Literal["ready", "coming_soon"]


def _p(
    *,
    id: str,
    label: str,
    can_speech_recognize: bool = False,
    can_interview_reason: bool = False,
    can_speech_speak: bool = False,
    recognize_via: RecognizeVia = "none",
    speak_via: SpeakVia = "none",
    status: ProviderStatus = "ready",
    default_model: str = "",
    default_api_base: str = "",
    hint: str = "",
) -> dict[str, Any]:
    return {
        "id": id,
        "label": label,
        "can_speech_recognize": can_speech_recognize,
        "can_interview_reason": can_interview_reason,
        "can_speech_speak": can_speech_speak,
        "recognize_via": recognize_via,
        "speak_via": speak_via,
        "status": status,
        "default_model": default_model,
        "default_api_base": default_api_base,
        "hint": hint,
    }

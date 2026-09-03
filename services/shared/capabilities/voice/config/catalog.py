"""三阶段语音/思考供应商能力目录（前后端共用语义）。

表结构与 ``_p`` 工厂在 :mod:`.catalog_schema`，三张表分别在
``reasoning_providers`` / ``recognize_providers`` / ``speak_providers``。
本模块聚合导出并实现 ``catalog_payload`` / ``find_provider``。
"""

from __future__ import annotations

from typing import Any

from .reasoning_providers import REASONING_PROVIDERS
from .recognize_providers import RECOGNIZE_PROVIDERS
from .speak_providers import SPEAK_PROVIDERS

__all__ = [
    "REASONING_PROVIDERS",
    "RECOGNIZE_PROVIDERS",
    "SPEAK_PROVIDERS",
    "catalog_payload",
    "find_provider",
    "non_reasoning_provider_ids",
]


def catalog_payload() -> dict[str, Any]:
    return {
        "reasoning": REASONING_PROVIDERS,
        "recognize": RECOGNIZE_PROVIDERS,
        "speak": SPEAK_PROVIDERS,
    }


def find_provider(stage: str, provider_id: str) -> dict[str, Any] | None:
    mapping = {
        "reasoning": REASONING_PROVIDERS,
        "recognize": RECOGNIZE_PROVIDERS,
        "speak": SPEAK_PROVIDERS,
    }
    for p in mapping.get(stage, []):
        if p["id"] == provider_id:
            return p
    return None


def non_reasoning_provider_ids() -> frozenset[str]:
    """不可担任「面试思考」的供应商 id 集合（单一真相，由目录派生）。

    = recognize/speak 目录全部 id − reasoning 目录中声明可思考的 id。
    供设置保存校验拒绝「把 ASR/TTS 供应商填到 reason 阶段」；
    新增语音供应商只需维护目录表，本集合自动跟随。
    """
    reason_capable = {
        p["id"]
        for p in REASONING_PROVIDERS
        if p.get("can_interview_reason")
    }
    voice_only = {
        p["id"]
        for table in (RECOGNIZE_PROVIDERS, SPEAK_PROVIDERS)
        for p in table
    }
    return frozenset(voice_only - reason_capable)

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

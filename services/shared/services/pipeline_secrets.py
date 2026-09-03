"""pipeline 配置的密钥与 extras JSON 辅助（叶子模块）。

- ``enc:`` 前缀加密语义（``SECRET_KEEP`` 表示保留现值）；
- extras 的响应侧脱敏（``public_extras``）与运行时解密（``runtime_extras``）。
"""

from __future__ import annotations

import json
from typing import Any

from shared.core.secrets import decrypt_secret, encrypt_secret

SECRET_KEEP = "keep"
SECRET_EXTRA_KEYS = frozenset({"asr_api_secret", "asr_access_key", "asr_app_key"})


def maybe_encrypt(value: str | None, current: str) -> str:
    if value is None or value == "" or value == SECRET_KEEP:
        return current
    if str(value).startswith("enc:"):
        return str(value)
    return encrypt_secret(value) or ""


def _dec(row: Any, name: str) -> str:
    raw = getattr(row, name, None) or ""
    if not raw:
        return ""
    text = str(raw)
    if not text.startswith("enc:"):
        return text
    try:
        return decrypt_secret(text) or ""
    except Exception as e:
        raise ValueError(f"密钥字段 {name} 解密失败，请到设置页重新保存密钥") from e


def parse_json(field: str | None) -> dict[str, Any]:
    if not field:
        return {}
    try:
        value = json.loads(field)
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def public_extras(extras: dict[str, Any]) -> dict[str, Any]:
    """不把旧版额外密钥回传到浏览器。"""
    return {key: value for key, value in extras.items() if key not in SECRET_EXTRA_KEYS}


def runtime_extras(extras: dict[str, Any]) -> dict[str, Any]:
    """读取兼容字段时解密旧版额外凭证。"""
    result = dict(extras)
    for key in SECRET_EXTRA_KEYS:
        value = result.get(key)
        if isinstance(value, str) and value.startswith("enc:"):
            result[key] = decrypt_secret(value) or ""
    return result

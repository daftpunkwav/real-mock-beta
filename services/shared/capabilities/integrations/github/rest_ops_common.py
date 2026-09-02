"""GitHub REST 公共辅助（错误判定与分页裁剪）。"""

from __future__ import annotations

from typing import Any


def _is_error(data: Any) -> bool:
    return isinstance(data, dict) and "error" in data


def _clamp_per_page(value: int, limit: int) -> int:
    return max(1, min(value, limit))

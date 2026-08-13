"""基础 API 服务模型。

候选人核心数据实体（UserProfile / Resume）为三服务共享，已归
``shared.models``；本文件保留 re-export 以兼容服务内引用。
"""

from __future__ import annotations

from shared.models import Resume, UserProfile  # noqa: F401

__all__ = ["Resume", "UserProfile"]

"""sessions.db 域 ORM 注册（组合根）。

业务包 models 须在 ``SessionsBase.metadata.create_all`` 之前 import，
但不应放在 ``shared.database`` 内（避免平台层反向依赖业务包）。
"""

from __future__ import annotations


def register_sessions_domain_models() -> None:
    """将 agent / interview 会话域表注册到 ``SessionsBase.metadata``。"""
    import agent_service.models  # noqa: F401
    import interview_service.models  # noqa: F401


__all__ = ["register_sessions_domain_models"]

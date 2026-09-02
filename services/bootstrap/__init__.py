"""应用组合根（启动期注册，非业务逻辑）。"""

from bootstrap.sessions_orm import register_sessions_domain_models

__all__ = ["register_sessions_domain_models"]

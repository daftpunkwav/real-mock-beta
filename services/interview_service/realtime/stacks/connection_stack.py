"""WS 连接层 mixin 聚合（lifecycle + auth + heartbeat）。"""

from interview_service.realtime.connection.auth import ConnectionAuthMixin
from interview_service.realtime.connection.heartbeat import HeartbeatMixin
from interview_service.realtime.connection.lifecycle import ConnectionLifecycleMixin


class ConnectionStackMixin(
    ConnectionLifecycleMixin,
    ConnectionAuthMixin,
    HeartbeatMixin,
):
    """连接建立、鉴权、心跳与主循环。"""


__all__ = ["ConnectionStackMixin"]

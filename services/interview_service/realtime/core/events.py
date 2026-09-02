"""面试会话事件类型与快照。

注意 ``SessionEvent.schema_version``：每次事件协议变更递增；前端可据此
做兼容判断。``SessionSnapshot`` 已归属 :mod:``interview_service.agents.snapshot``，此处仅
向后兼容 re-export。
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from interview_service.agents.snapshot import SessionSnapshot


class TurnState(str, Enum):
    AI_SPEAKING = "AI_SPEAKING"
    USER_SPEAKING = "USER_SPEAKING"
    PROCESSING = "PROCESSING"
    IDLE = "IDLE"


@dataclass
class SessionEvent:
    type: str
    payload: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    # 事件协议版本，演进时 +1；ws_handler 在首个事件注入
    schema_version: int = 1


__all__ = ["TurnState", "SessionEvent", "SessionSnapshot"]

# SessionSnapshot 已迁移至 interview_service.agents.snapshot；此处 re-export 仅为向后兼容。
# 旧调用方 from interview_service.realtime.events import SessionSnapshot 仍可用，新代码应直接
# 从 interview_service.agents.snapshot 引用（解耦方向：realtime → agents 单向）。

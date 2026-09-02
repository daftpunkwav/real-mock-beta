"""话轮层 mixin 聚合（coordinator + streaming + control）。"""

from interview_service.realtime.turn.coordinator import TurnCoordinatorMixin
from interview_service.realtime.turn.control import TurnControlMixin
from interview_service.realtime.turn.streaming import TurnStreamingMixin


class TurnStackMixin(
    TurnCoordinatorMixin,
    TurnStreamingMixin,
    TurnControlMixin,
):
    """候选人回合、流式消费与打断/收尾。"""


__all__ = ["TurnStackMixin"]

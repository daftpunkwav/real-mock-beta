"""话轮锁（WS mixin）：候选人回合的占用/释放与 epoch 校验。

拆自 :mod:`...turn_coordinator`。只负责锁语义，不碰流式消费与 STT。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from interview_service.realtime.context import ConnectionContext


class TurnLockMixin:
    """话轮锁：``closing`` 拒绝；busy 且 epoch 未变拒绝；只释放本 epoch。"""

    ctx: "ConnectionContext"

    def _can_start_user_turn(self) -> bool:
        """是否允许启动新的候选人回合（含打断后接棒）。"""
        if self.ctx.closing:
            return False
        if not self.ctx.turn_busy:
            return True
        return self.ctx.busy_epoch != self.ctx.stream_epoch

    def _begin_user_turn(self) -> int | None:
        """占用回合锁并绑定当前 epoch；不可启动时返回 None。"""
        if not self._can_start_user_turn():
            return None
        epoch = self.ctx.stream_epoch
        self.ctx.turn_busy = True
        self.ctx.busy_epoch = epoch
        return epoch

    def _end_user_turn(self, epoch: int) -> None:
        """仅当仍是本回合占用时释放锁。"""
        if self.ctx.busy_epoch == epoch:
            self.ctx.turn_busy = False


__all__ = ["TurnLockMixin"]

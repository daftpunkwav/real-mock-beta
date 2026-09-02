"""候选人文字入轮（WS mixin）：先 ``stt_final`` 再进主流程。

拆自 :mod:`...turn_coordinator`。只做文字回合的编排，锁语义在
:class:`TurnLockMixin`，主流程消费在 ``user_text_control.UserTextControlMixin``。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any


from shared.database import SessionLocal
from interview_service.realtime.core.events import TurnState

if TYPE_CHECKING:
    from interview_service.realtime.core.context import ConnectionContext

logger = logging.getLogger(__name__)


class TurnTextEntryMixin:
    """文字入轮：占用锁 → 发 ``stt_final`` → 主流程；失败回 ``USER_SPEAKING``。"""

    ctx: "ConnectionContext"

    async def _run_user_text(
        self,
        text: str,
        data: dict[str, Any],
    ) -> None:
        epoch = self._begin_user_turn()
        if epoch is None:
            return
        db = SessionLocal()
        try:
            session = self._load_session(db)
            if not session:
                return
            await self.set_turn(TurnState.PROCESSING)
            await self.send("stt_final", text=text)
            await self._process_user_text(text, data, db, session)
        except Exception:
            logger.exception("user_text 回合失败 sid=%s", self.ctx.session_id)
            try:
                if epoch == self.ctx.stream_epoch:
                    await self.set_turn(TurnState.USER_SPEAKING)
            except Exception:
                logger.debug(
                    "user_text 恢复 USER_SPEAKING 失败 sid=%s",
                    self.ctx.session_id,
                    exc_info=True,
                )
        finally:
            self._end_user_turn(epoch)
            try:
                db.close()
            except Exception:
                logger.debug(
                    "user_text DB close 失败 sid=%s",
                    self.ctx.session_id,
                    exc_info=True,
                )


__all__ = ["TurnTextEntryMixin"]

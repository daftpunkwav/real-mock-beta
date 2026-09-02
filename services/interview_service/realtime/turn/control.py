"""话轮副作用：打断、收尾、静默追问、事件分发（WS mixin 组合）。

职责拆分到独立子模块，本模块只做 mixin 组合：

- :mod:`interrupt_control` — 打断计数与处理；
- :mod:`user_text_control` — 用户文本入轮；
- :mod:`finish_control` — 主动收尾；
- :mod:`event_dispatch` — StreamEvent 分发；
- :mod:`silence_nudge` — 静默追问编排（LLM 生成仍在 :mod:`silence_probe`）。
"""

from __future__ import annotations

from interview_service.realtime.core.event_dispatch import EventDispatchMixin
from interview_service.realtime.control.finish import FinishControlMixin
from interview_service.realtime.control.interrupt import InterruptControlMixin
from interview_service.realtime.control.silence_nudge import SilenceNudgeMixin
from interview_service.realtime.control.silence_probe import SilenceProbeMixin
from interview_service.realtime.control.user_text import UserTextControlMixin


class TurnControlMixin(
    InterruptControlMixin,
    UserTextControlMixin,
    FinishControlMixin,
    EventDispatchMixin,
    SilenceNudgeMixin,
    SilenceProbeMixin,
):
    """话轮副作用组合；依赖 ctx 中的状态字段 + 继承的方法。"""


__all__ = ["TurnControlMixin"]

"""回合协调（WS mixin）：话轮锁、候选人回合；流式/副作用委托子 mixin。

本模块只做组合：

- :mod:`turn_lock` — 话轮锁（closing 拒绝 / busy+epoch 校验 / 只释放本 epoch）；
- :mod:`turn_text_entry` — 候选人文字入轮（先 ``stt_final`` 再主流程）；
- :mod:`turn_stt_finish` — 语音回合收尾（PCM 超限 / 回采 / 失败计数）；
- :mod:`turn_playback` — 播放等待（世代对齐、等播完再开麦）。

``transcribe_utterance_result`` 与 ``_AUDIO_BUFFER_MAX_BYTES`` 由本模块再导出
（测试 patch / import 路径保持不变）。
"""

from __future__ import annotations

# 测试 patch 目标：测试 patch "interview_service.realtime.turn.coordinator.
# transcribe_utterance_result"（改写本模块的模块级名字）。turn_stt_finish 的
# 调用点从本模块动态读取同名属性，patch 后随之命中。
from shared.capabilities.voice.stt import transcribe_utterance_result  # noqa: F401 — 测试 patch 目标

from interview_service.realtime.turn.control import TurnControlMixin
from interview_service.realtime.turn.lock import TurnLockMixin
from interview_service.realtime.turn.playback import TurnPlaybackMixin
from interview_service.realtime.turn.stt_finish import (
    TurnSttFinishMixin,
    _AUDIO_BUFFER_MAX_BYTES,
)
from interview_service.realtime.turn.streaming import TurnStreamingMixin, _IMAGE_BASE64_MAX_LEN
from interview_service.realtime.turn.text_entry import TurnTextEntryMixin


class TurnCoordinatorMixin(
    TurnLockMixin,
    TurnTextEntryMixin,
    TurnSttFinishMixin,
    TurnPlaybackMixin,
    TurnStreamingMixin,
    TurnControlMixin,
):
    """候选人回合入口；组合流式消费与打断/收尾副作用。"""


__all__ = [
    "TurnCoordinatorMixin",
    "TurnLockMixin",
    "TurnTextEntryMixin",
    "TurnSttFinishMixin",
    "TurnPlaybackMixin",
    "transcribe_utterance_result",
    "_AUDIO_BUFFER_MAX_BYTES",
    "_IMAGE_BASE64_MAX_LEN",
]

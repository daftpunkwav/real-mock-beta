"""面试回合事件类型定义。

为 runner 与 ws_handler 之间提供统一的流式契约，避免 handler 直接访问 agent 私有状态。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class EventKind(str, Enum):
    """runner 推送给上层的所有事件类型。"""

    TOKEN = "token"               # 流式 token
    TURN_COMPLETE = "turn_done"   # 单个回合完成（含完整文本与阶段信息）
    ERROR = "error"               # 异常


@dataclass(frozen=True)
class StreamEvent:
    """runner -> ws_handler / API 的事件载体。"""

    kind: EventKind
    token: str = ""
    content: str = ""             # 完整文本（仅 TURN_COMPLETE 时填充；协议下为 say 纯文本）
    phase_id: str = ""            # 当前阶段 id
    is_complete: bool = False     # 是否面试整体结束（interview_complete）
    phase_changed: bool = False   # 本回合是否切换了阶段
    emotion: str = "neutral"      # 情感标签（turn 协议 emotion 字段）
    error: str = ""               # 错误信息
    error_code: str = ""          # 业务错误码（如 C0001）；空时前端按 B0001 兜底
    error_retryable: bool = False # 是否可重试
    wait_seconds: int = 0         # 预计候选人作答秒数（0=未提供）
    sources: tuple[str, ...] = () # 本轮作答依据（resume/github/company_kb/none）

    @classmethod
    def make_token(cls, token: str) -> "StreamEvent":
        return cls(kind=EventKind.TOKEN, token=token)

    @classmethod
    def make_turn_done(
        cls,
        *,
        content: str,
        phase_id: str,
        is_complete: bool,
        phase_changed: bool,
        emotion: str = "neutral",
        wait_seconds: int = 0,
        sources: tuple[str, ...] = (),
    ) -> "StreamEvent":
        return cls(
            kind=EventKind.TURN_COMPLETE,
            content=content,
            phase_id=phase_id,
            is_complete=is_complete,
            phase_changed=phase_changed,
            emotion=emotion,
            wait_seconds=wait_seconds,
            sources=sources,
        )

    @classmethod
    def make_error(
        cls,
        message: str,
        *,
        code: str = "",
        retryable: bool = False,
    ) -> "StreamEvent":
        """构造错误事件。code 为业务错误码；为空时前端按 B0001 兜底显示。"""
        return cls(
            kind=EventKind.ERROR,
            error=message,
            error_code=code,
            error_retryable=retryable,
        )


__all__ = ["EventKind", "StreamEvent"]
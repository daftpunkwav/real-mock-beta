"""面试回合输出的语义解析：协议控制字段 → 强类型默认值。

机制层（say-first 流式提取）见 :mod:`shared.capabilities.ai.llm.say_first_stream`；
本模块只负责把控制 dict 校验成强类型并补默认值——任何字段缺失/类型漂移
都只降级自身，不影响 say 语音通道。

``wait_seconds`` 语义：0 表示模型未提供，消费方按题型/阶段取默认；
其余值钳位 0-120（"等待"场景的下限由消费方施加，收尾回合不需要等待）。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

_PROTOCOL_VERSION = 1
_EMOTIONS = ("neutral", "smile", "serious")
_SOURCE_VALUES = ("resume", "github", "company_kb", "none")
_WAIT_MAX = 120


@dataclass(frozen=True)
class TurnScore:
    """上一轮候选人回答的即时简评（供下一轮 prompt 与报告复用）。"""

    brief: str = ""
    rating: int = 0          # 1-5；0=未提供
    weak_points: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class TurnOutput:
    """一个回合的结构化输出。"""

    say: str = ""
    protocol_version: int = 0
    wait_seconds: int = 0
    emotion: str = "neutral"
    phase_complete: bool = False
    interview_complete: bool = False
    turn_score: TurnScore | None = None
    probe: str | None = None
    sources: tuple[str, ...] = ()
    degraded: bool = False   # True=未拿到结构化控制区（全部默认值）


def parse_turn_output(
    controls: dict | None,
    *,
    say_text: str,
    degraded: bool = False,
) -> TurnOutput:
    """控制 dict → TurnOutput；类型漂移逐字段兜默认，只记日志不抛错。"""
    if not isinstance(controls, dict):
        return TurnOutput(say=say_text, degraded=True)

    version = controls.get("v")
    if not isinstance(version, int) or isinstance(version, bool):
        version = 0

    wait_seconds = controls.get("wait_seconds")
    if isinstance(wait_seconds, bool) or not isinstance(wait_seconds, int):
        wait_seconds = 0
    elif wait_seconds < 0:
        wait_seconds = 0
    elif wait_seconds > _WAIT_MAX:
        wait_seconds = _WAIT_MAX

    emotion = controls.get("emotion")
    if emotion not in _EMOTIONS:
        emotion = "neutral"

    phase_complete = controls.get("phase_complete") is True
    interview_complete = controls.get("interview_complete") is True

    turn_score = _parse_turn_score(controls.get("turn_score"))

    probe = controls.get("probe")
    if probe is not None:
        probe = str(probe).strip()[:200] or None

    sources = _parse_sources(controls.get("sources"))

    if version != _PROTOCOL_VERSION:
        logger.debug("回合输出协议版本 v=%s（当前 %s）", version, _PROTOCOL_VERSION)

    return TurnOutput(
        say=say_text,
        protocol_version=version,
        wait_seconds=wait_seconds,
        emotion=emotion,
        phase_complete=phase_complete,
        interview_complete=interview_complete,
        turn_score=turn_score,
        probe=probe,
        sources=sources,
        degraded=degraded,
    )


def _parse_turn_score(raw: object) -> TurnScore | None:
    """turn_score 形状校验：非 dict → None；字段逐个兜默认。"""
    if not isinstance(raw, dict):
        return None
    brief = str(raw.get("brief") or "").strip()[:200]
    rating = raw.get("rating")
    if isinstance(rating, bool) or not isinstance(rating, int):
        rating = 0
    rating = max(0, min(5, rating))
    points_raw = raw.get("weak_points")
    points: list[str] = []
    if isinstance(points_raw, list):
        for p in points_raw[:2]:
            text = str(p or "").strip()[:120]
            if text:
                points.append(text)
    if not brief and not rating and not points:
        return None
    return TurnScore(brief=brief, rating=rating, weak_points=tuple(points))


def _parse_sources(raw: object) -> tuple[str, ...]:
    """sources 白名单过滤；未知值丢弃，空集视为空。"""
    if not isinstance(raw, list):
        return ()
    out: list[str] = []
    for item in raw[:4]:
        value = str(item or "").strip().lower()
        if value in _SOURCE_VALUES and value not in out:
            out.append(value)
    return tuple(out)


__all__ = ["TurnOutput", "TurnScore", "parse_turn_output"]

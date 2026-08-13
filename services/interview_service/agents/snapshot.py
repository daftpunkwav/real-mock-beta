"""会话快照：各子 Agent 写入的最新状态容器。

归属 agents 层（所有者是 :class:`interview_service.agents.orchestrator.InterviewOrchestrator`）。
realtime 层只负责写入（视觉/STT 数据）与读取，依赖方向保持 realtime → agents 单向。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class SessionSnapshot:
    """各 Agent 写入的最新状态快照。"""

    stt_partial: str = ""
    stt_final: str = ""
    vision_summary: str = ""
    face_analysis: dict[str, Any] = field(default_factory=dict)
    last_user_text: str = ""
    token_usage: int = 0
    phase: str = ""
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def merge_face(self, face: dict[str, Any] | None) -> None:
        if not face:
            return
        self.face_analysis = face
        hints: list[str] = []
        if not face.get("face_detected", True):
            hints.append("未检测到人脸")
        elif face.get("looking_away"):
            hints.append("未看镜头")
        if face.get("nervousness", 0) > 0.5:
            hints.append("略显紧张")
        if hints:
            self.vision_summary = "候选人状态：" + "、".join(hints)
        self.updated_at = datetime.now(timezone.utc)


__all__ = ["SessionSnapshot"]

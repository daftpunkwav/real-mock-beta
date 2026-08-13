"""视觉 Agent：汇总候选人视频状态。"""

from typing import Any


class VisionAgent:
    """将面部分析与可选帧摘要合并为文字状态。"""

    @staticmethod
    def summarize(face_analysis: dict[str, Any] | None) -> str:
        if not face_analysis:
            return ""
        hints: list[str] = []
        if not face_analysis.get("face_detected", True):
            hints.append("画面中未检测到人脸")
        elif face_analysis.get("looking_away"):
            hints.append("候选人未直视镜头")
        nervousness = face_analysis.get("nervousness", 0)
        if isinstance(nervousness, (int, float)) and nervousness > 0.5:
            hints.append("候选人显得紧张")
        if face_analysis.get("face_count", 1) > 1:
            hints.append("画面中出现多人")
        return "；".join(hints) if hints else "候选人状态正常"

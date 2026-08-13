"""面试统筹 Agent：合并多源快照、静默追问。"""

from __future__ import annotations

import random

from interview_service.agents.snapshot import SessionSnapshot


class InterviewOrchestrator:
    """读取各子 Agent 快照，生成增强上下文与静默追问。"""

    def __init__(self) -> None:
        self.snapshot = SessionSnapshot()

    def build_context_prefix(self) -> str:
        parts: list[str] = []
        if self.snapshot.vision_summary:
            parts.append(f"[视觉状态：{self.snapshot.vision_summary}]")
        return " ".join(parts)

    def build_silence_nudge(
        self,
        personality: str,
        strictness: int,
        phase: str | None = None,
    ) -> str:
        """按阶段/人设生成自然追问，同档内随机，避免句句相同。"""
        phase_id = (phase or "").strip().lower()
        if phase_id in {"identity_check", "identity", "identity_confirm"}:
            return random.choice(
                [
                    "方便的话，直接确认一下刚才的信息是否属实就好。",
                    "你可以简单说「确认无误」，或指出需要更正的地方。",
                    "没关系，先口头确认身份信息，我们再往下聊。",
                    "若环境没问题，回我一句确认，我们就开始正式面试。",
                ]
            )
        if phase_id in {"self_intro", "introduction"}:
            return random.choice(
                [
                    "可以从最近一段经历或最想强调的项目开始。",
                    "不需要很完整，先讲两分钟自我介绍即可。",
                    "你更想先聊项目，还是先介绍背景？",
                ]
            )

        is_strict = strictness >= 6 or personality in ("pressure", "expert")
        if is_strict:
            tiers = [
                [
                    "你已经思考了一会儿了，先说出结论也行。",
                    "我们可以先抓重点：你的核心观点是什么？",
                ],
                [
                    "时间有限，请尽快给出你的看法。",
                    "不妨先用一两句话概括，再展开细节。",
                ],
                [
                    "我需要你更具体一些，请现在回答。",
                    "请直接回应问题，避免绕开关键点。",
                ],
            ]
        else:
            tiers = [
                [
                    "没关系，可以先说说你的想法，哪怕不完整也没关系。",
                    "你先开口就好，我们一起把思路理清楚。",
                    "卡住的话，可以从你最熟悉的一点讲起。",
                ],
                [
                    "你可以从印象最深的一点开始说起。",
                    "想先讲背景、过程，还是结果？任选一个切口。",
                ],
                [
                    "需要我换个角度提问吗？或者你先讲讲相关背景？",
                    "如果你愿意，我可以先给一个更具体的子问题。",
                ],
            ]
        # 1-4 -> 0，5-8 -> 1，9-10 -> 2
        idx = max(0, min((strictness - 1) // 4, len(tiers) - 1))
        if personality in ("pressure", "expert"):
            idx = max(idx, 1)
        return random.choice(tiers[idx])

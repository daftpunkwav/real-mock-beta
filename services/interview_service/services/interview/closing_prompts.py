"""收尾发言的提示词与阶段跳转（纯数据/策略，供 InterviewRunner.stream_closing 使用）。"""

from __future__ import annotations

from interview_service.services.interview.session_state import InterviewSessionState

# 不同人设下的收尾语气提示（保持原有文案）
CLOSING_BY_PERSONALITY: dict[str, str] = {
    "gentle": "语气温暖鼓励，肯定准备与态度，温和指出 1-2 个可改进点。",
    "professional": "语气专业克制，给出结构化口头评价（优势/待提升），感谢配合。",
    "pressure": "保持一定锐利但不刻薄，点出扛压表现与薄弱处，仍须正式致谢。",
    "hr": "侧重软技能与文化匹配感受，鼓励后续沟通，致谢。",
    "expert": "从技术深度点评亮点与缺口，专业致谢。",
}


def closing_system_prompt(style_hint: str) -> str:
    """构造「结束面试」的 system 提示。"""
    nl = "\n"
    return (
        "候选人主动点击了「结束面试」。请立刻做口头收尾，不要再提问、不要开启新考察。"
        + nl
        + "要求："
        + nl
        + "1. 感谢候选人参加本次模拟面试；"
        + nl
        + "2. 结合本场已聊内容，用 3–6 句给出个性化口头总结与评价"
        + "（至少各提一点优势与待改进）；若对话很少，也可基于态度与表达作简要评价；"
        + nl
        + f"3. 人设与语气：{style_hint}"
        + nl
        + "4. 不要输出表格或报告标题；不要捏造未提及的项目细节；"
        + nl
        + "5. 把回复中的 interview_complete 设为 true"
    )


def jump_to_summary_phase(state: InterviewSessionState, phase_ids: list[str]) -> bool:
    """收尾前把阶段索引跳到 summary（若尚未到达），返回是否发生跳转。

    同时重置当前阶段提问计数并同步 session.current_phase，与 runner 原逻辑一致。
    """
    summary_idx = next(
        (i for i, pid in enumerate(phase_ids) if pid == "summary"),
        max(0, len(phase_ids) - 1),
    )
    if state.current_phase_idx < summary_idx:
        state.current_phase_idx = summary_idx
        state.questions_in_phase = 0
        state.session.current_phase = phase_ids[summary_idx]
        return True
    return False


__all__ = [
    "CLOSING_BY_PERSONALITY",
    "closing_system_prompt",
    "jump_to_summary_phase",
]

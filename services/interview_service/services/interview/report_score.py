"""报告评分辅助：话轮礼貌扣分与明确不落库的降级兜底。"""

from __future__ import annotations

import json

from interview_service.models import InterviewSession
from interview_service.schemas import InterviewReport, ScoreBreakdown


def _fallback_report() -> InterviewReport:
    return InterviewReport(
        overall_score=70,
        score_breakdown=ScoreBreakdown(
            overall=70, technical=70, communication=70,
            project_depth=70, problem_solving=70, presence=70, politeness=70,
        ),
        weaknesses=["报告生成时遇到错误，请重试"],
        improvement_suggestions=["完成更多面试练习以获得准确评估"],
    )


def _apply_interrupt_politeness_penalty(
    session: InterviewSession,
    report: InterviewReport,
) -> InterviewReport:
    """候选人打断面试官：硬性下调礼貌/表达分，避免模型忽略统计。"""
    try:
        state = json.loads(session.agent_state or "{}")
        c_int = int(state.get("candidate_interrupts") or 0) if isinstance(state, dict) else 0
    except Exception:
        c_int = 0
    if c_int <= 0:
        return report
    sb = report.score_breakdown
    penalty = min(30, c_int * 6)
    sb.politeness = max(0, (sb.politeness or 75) - penalty)
    sb.communication = max(0, sb.communication - max(2, penalty // 2))
    sb.presence = max(0, sb.presence - max(1, penalty // 3))
    # 略微拉动总分
    dims = [
        sb.technical,
        sb.communication,
        sb.project_depth,
        sb.problem_solving,
        sb.presence,
        sb.politeness,
    ]
    sb.overall = int(round(sum(dims) / len(dims)))
    report.overall_score = sb.overall
    tip = f"本场打断面试官 {c_int} 次，话轮礼仪有扣分；建议等对方说完再接话。"
    if tip not in report.interview_suggestions:
        report.interview_suggestions = [tip, *list(report.interview_suggestions or [])]
    return report

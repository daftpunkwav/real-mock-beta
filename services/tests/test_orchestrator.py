"""InterviewOrchestrator 单元测试，重点覆盖静默追问索引算法。"""

from __future__ import annotations

from interview_service.agents.orchestrator import InterviewOrchestrator


def test_silence_nudge_strict_branch_uses_strict_templates() -> None:
    """压力人格应走严格分支模板。"""
    orch = InterviewOrchestrator()
    for _ in range(12):
        nudge = orch.build_silence_nudge("pressure", strictness=3)
        assert any(
            k in nudge
            for k in ("结论", "核心观点", "时间有限", "一两句话", "更具体", "直接回应")
        ), nudge


def test_silence_nudge_gentle_branch_uses_gentle_templates() -> None:
    """温和人格 + 低严格度应走温柔分支模板。"""
    orch = InterviewOrchestrator()
    for _ in range(12):
        nudge = orch.build_silence_nudge("gentle", strictness=1)
        assert any(
            k in nudge
            for k in ("没关系", "想法", "开口", "熟悉", "印象最深", "换个角度", "子问题", "背景")
        ), nudge


def test_silence_nudge_low_strictness_uses_first_tier() -> None:
    """严格度 1-4 应命中第 0 档温柔模板。"""
    orch = InterviewOrchestrator()
    for s in (1, 2, 3, 4):
        for _ in range(8):
            nudge = orch.build_silence_nudge("professional", strictness=s)
            assert any(
                k in nudge for k in ("没关系", "想法", "开口", "熟悉")
            ), f"strictness={s}: {nudge}"


def test_silence_nudge_mid_strictness_uses_second_tier() -> None:
    """严格度 5-8：5 走温柔中档，>=6 走严格中档。"""
    orch = InterviewOrchestrator()
    for s in (5, 6, 7, 8):
        for _ in range(8):
            nudge = orch.build_silence_nudge("professional", strictness=s)
            if s >= 6:
                assert any(
                    k in nudge for k in ("时间有限", "一两句话", "概括")
                ), f"strictness={s}: {nudge}"
            else:
                assert any(
                    k in nudge for k in ("印象最深", "背景", "过程", "结果", "切口")
                ), f"strictness={s}: {nudge}"


def test_silence_nudge_max_strictness_uses_last_tier() -> None:
    """严格度 9-10 应命中最直接档。"""
    orch = InterviewOrchestrator()
    for s in (9, 10):
        for _ in range(8):
            nudge = orch.build_silence_nudge("professional", strictness=s)
            assert any(
                k in nudge for k in ("更具体", "直接回应", "关键点")
            ), f"strictness={s}: {nudge}"


def test_silence_nudge_identity_phase_is_contextual() -> None:
    """身份确认阶段应使用阶段专属文案。"""
    orch = InterviewOrchestrator()
    for _ in range(10):
        nudge = orch.build_silence_nudge(
            "professional", strictness=1, phase="identity_check"
        )
        assert any(
            k in nudge for k in ("确认", "身份", "属实", "正式面试")
        ), nudge


def test_silence_nudge_normal_strictness_not_skips_first_template() -> None:
    """回归：正常严格度(1)应落在最温和档。"""
    orch = InterviewOrchestrator()
    nudge = orch.build_silence_nudge("professional", strictness=1)
    assert any(k in nudge for k in ("没关系", "想法", "开口", "熟悉")), nudge

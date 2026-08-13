"""followup 信号分析器单元测试。"""

from __future__ import annotations

from interview_service.services.interview.followup import analyze


def test_empty_answer_triggers_missing_data() -> None:
    sig = analyze("")
    assert sig.needs_followup
    assert sig.category == "missing_data"


def test_vague_terms_short_answer_triggers_vague() -> None:
    sig = analyze("差不多就是这样吧", question="请描述一次性能优化")
    assert sig.needs_followup
    assert sig.category == "vague"


def test_long_answer_without_data_triggers_missing_data() -> None:
    sig = analyze(
        "我们对这个接口进行了完整的性能优化工作，从架构设计到代码实现"
        "都做了深入的改进，整体效果非常好，用户反馈也很满意。",
        question="请说说这次性能优化的具体效果",
    )
    assert sig.needs_followup
    assert sig.category == "missing_data"


def test_answer_with_quantitative_data_passes() -> None:
    sig = analyze(
        "接口 RT 从 200ms 降至 35ms，QPS 从 1.2k 提升到 8k，错误率下降 90%。",
        question="请说说这次性能优化的具体效果",
    )
    assert not sig.needs_followup


def test_off_topic_low_overlap_triggers_off_topic() -> None:
    sig = analyze(
        "我平时喜欢打篮球，周末会和朋友去爬山。",
        question="请介绍一个你最有成就感的项目，并说明你在其中的角色。",
    )
    assert sig.needs_followup
    assert sig.category == "off_topic"


def test_tech_hole_triggers_when_no_domain_match() -> None:
    sig = analyze(
        "我做了用户调研和需求分析，与产品经理合作完成了 PRD 撰写。",
        question="请介绍你的技术项目",
        tech_domains=["Python", "FastAPI", "PostgreSQL"],
    )
    assert sig.needs_followup
    assert sig.category == "tech_hole"


def test_answer_with_tech_keywords_passes() -> None:
    sig = analyze(
        "我们使用 FastAPI 重构了接口，配合 PostgreSQL 索引优化，"
        "QPS 提升至 1.2 万。",
        question="请介绍你的技术项目",
        tech_domains=["Python", "FastAPI", "PostgreSQL"],
    )
    assert not sig.needs_followup


def test_suggested_probe_is_non_empty_when_followup() -> None:
    sig = analyze("可能差不多吧", question="自我介绍")
    assert sig.suggested_probe
    assert len(sig.suggested_probe) > 5


def test_missing_data_skipped_in_reverse_qa_phase() -> None:
    """反问环节不应触发 missing_data（候选人提问无需量化数据）。"""
    sig = analyze(
        "我想了解一下贵公司的技术栈和团队协作方式，以及新人培养机制。",
        question="现在你可以向我提问",
        phase_id="reverse_qa",
    )
    assert not sig.needs_followup


def test_tech_hole_skipped_in_summary_phase() -> None:
    """总结环节不应触发 tech_hole。"""
    sig = analyze(
        "面试官做了总结评价，感谢候选人的时间。",
        question="请做总结",
        tech_domains=["Python", "FastAPI"],
        phase_id="summary",
    )
    assert not sig.needs_followup


def test_missing_data_still_triggers_in_technical_phase() -> None:
    """考察类阶段（project_deep_dive）仍应正常触发 missing_data。"""
    sig = analyze(
        "我们对这个接口进行了完整的性能优化工作，从架构设计到代码实现"
        "都做了深入的改进，整体效果非常好。",
        question="请说说性能优化的效果",
        phase_id="project_deep_dive",
    )
    assert sig.needs_followup
    assert sig.category == "missing_data"


def test_vague_still_triggers_in_reverse_qa_phase() -> None:
    """模糊词在任何阶段都应触发（包括反问环节）。"""
    sig = analyze(
        "大概可能就是想了解一下公司情况吧",
        question="你想了解什么",
        phase_id="reverse_qa",
    )
    assert sig.needs_followup
    assert sig.category == "vague"
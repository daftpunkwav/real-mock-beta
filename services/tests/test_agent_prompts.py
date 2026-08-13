"""``app.services.interview.agent_prompts.build_system_prompt`` 单元测试。

覆盖：
- 无 candidate（简历未绑定）时正常组装；
- 带 candidate（含 projects / work_experience）时正常序列化，不抛 NameError
  （回归：F821 `json` 未 import 的运行时崩溃）；
- followup_probe 注入追问引导段落；
- profile 个人档案段落。
"""

from __future__ import annotations

from shared.schemas import CandidateProfile
from interview_service.schemas import InterviewConfig
from interview_service.services.interview.agent_prompts import build_system_prompt
from interview_service.services.interview.workflows import get_workflow


def _config(**overrides) -> InterviewConfig:
    base = {
        "role": "后端工程师",
        "level": "高级",
        "company": "字节跳动",
    }
    base.update(overrides)
    return InterviewConfig(**base)


def _candidate(**overrides) -> CandidateProfile:
    base = {
        "name": "张三",
        "skills": ["Python", "FastAPI"],
        "projects": [{"name": "MockInterviewApp", "desc": "AI 模拟面试"}],
        "work_experience": [{"company": "某厂", "role": "后端"}],
    }
    base.update(overrides)
    return CandidateProfile(**base)


def test_without_candidate_and_profile() -> None:
    """无 candidate / profile 时正常组装，含基本段落。"""
    prompt = build_system_prompt(
        config=_config(),
        candidate=None,
        company_context="公司简介：做 AI 面试产品",
        workflow=get_workflow("technical"),
        current_phase=get_workflow("technical").phases[0],
    )
    assert "公司简介" in prompt
    assert "面试官" in prompt


def test_with_candidate_serializes_projects() -> None:
    """带 candidate 时 projects/work_experience 应被 json.dumps 序列化（回归 F821）。"""
    prompt = build_system_prompt(
        config=_config(),
        candidate=_candidate(),
        company_context="",
        workflow=get_workflow("technical"),
        current_phase=get_workflow("technical").phases[0],
    )
    assert "张三" in prompt
    assert "MockInterviewApp" in prompt  # projects 内容出现
    assert "某厂" in prompt  # work_experience 内容出现


def test_with_followup_probe_injects_section() -> None:
    """followup_probe 应注入追问引导段落。"""
    prompt = build_system_prompt(
        config=_config(),
        candidate=None,
        company_context="",
        workflow=get_workflow("technical"),
        current_phase=get_workflow("technical").phases[0],
        followup_probe="候选人提到系统设计薄弱，请深入追问缓存一致性。",
    )
    assert "追问引导" in prompt
    assert "缓存一致性" in prompt


def test_with_profile_includes_personal_info() -> None:
    """带 profile 时输出候选人个人档案段落。"""
    from shared.models import UserProfile

    profile = UserProfile(
        name="李四",
        school="某大学",
        self_intro="5 年后端经验",
        job_direction="后端",
        target_role="高级后端",
        tech_domains='["Python", "Go"]',
    )
    prompt = build_system_prompt(
        config=_config(),
        candidate=None,
        company_context="",
        workflow=get_workflow("technical"),
        current_phase=get_workflow("technical").phases[0],
        profile=profile,
    )
    assert "个人档案" in prompt
    assert "李四" in prompt

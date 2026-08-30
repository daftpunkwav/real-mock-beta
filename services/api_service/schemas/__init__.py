"""基础 API 服务契约：用户档案与简历域。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from shared.schemas import CandidateProfile  # noqa: F401  # 共享档案契约 re-export


# ── 用户档案 ──────────────────────────────────────────

class UserProfileUpdate(BaseModel):
    name: str = "求职者"
    gender: str = ""
    identity: str = ""
    school: str = ""
    major: str = ""
    graduation_year: str = ""
    job_direction: str = ""
    experience_years: str = ""
    work_years_detail: str = ""
    current_company: str = ""
    expected_salary: str = ""
    self_intro: str = ""
    tech_domains: list[str] = Field(default_factory=list)
    target_role: str = ""
    github_username: str = ""
    portfolio_url: str = ""
    linkedin_url: str = ""
    city: str = ""
    preferred_languages: str = ""
    career_highlights: str = ""
    open_to_remote: str = ""
    notice_period: str = ""
    education_level: str = ""
    expected_city: str = ""
    email: str = ""
    phone: str = ""
    certificates: str = ""
    english_level: str = ""
    signature_projects: str = ""
    strengths: str = ""
    weaknesses: str = ""


class UserProfileResponse(BaseModel):
    id: int
    name: str
    gender: str = ""
    identity: str = ""
    school: str = ""
    major: str = ""
    graduation_year: str = ""
    job_direction: str
    experience_years: str
    work_years_detail: str = ""
    current_company: str = ""
    expected_salary: str = ""
    self_intro: str = ""
    tech_domains: list[str]
    target_role: str
    github_username: str = ""
    portfolio_url: str = ""
    linkedin_url: str = ""
    city: str = ""
    preferred_languages: str = ""
    career_highlights: str = ""
    open_to_remote: str = ""
    notice_period: str = ""
    education_level: str = ""
    expected_city: str = ""
    email: str = ""
    phone: str = ""
    certificates: str = ""
    english_level: str = ""
    signature_projects: str = ""
    strengths: str = ""
    weaknesses: str = ""
    updated_at: datetime | None = None


# ── 简历 ──────────────────────────────────────────

class ResumeResponse(BaseModel):
    id: int
    filename: str
    file_type: str
    parsed_profile: CandidateProfile
    is_active: bool = False
    score: int | None = None
    analysis: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class DimensionScore(BaseModel):
    """简历评价单维度得分。"""
    score: int = Field(ge=0, le=100)
    comment: str = ""


class RewriteExample(BaseModel):
    """简历 bullet 改写对照。"""
    before: str = ""
    after: str = ""


class ResumeAnalysis(BaseModel):
    """多维度简历 Agent 评价结果。

    兼容旧字段 strengths/weaknesses/…，并扩展 dimension_scores 等。
    """
    score: int = Field(ge=0, le=100)
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    improvement_suggestions: list[str] = Field(default_factory=list)
    predicted_questions: list[str] = Field(default_factory=list)
    # 扩展：多维度
    dimension_scores: dict[str, DimensionScore] = Field(default_factory=dict)
    ats_keywords: list[str] = Field(default_factory=list)
    missing_keywords: list[str] = Field(default_factory=list)
    project_deep_dive: list[str] = Field(default_factory=list)
    red_flags: list[str] = Field(default_factory=list)
    role_fit_summary: str = ""
    seniority_estimate: str = ""
    rewrite_examples: list[RewriteExample] = Field(default_factory=list)
    interview_risk_areas: list[str] = Field(default_factory=list)
    overall_narrative: str = ""
    # 排版 / 内容深评 + 市场参考
    layout_review: str = ""
    typography_review: str = ""
    content_review: str = ""
    market_insights: list[str] = Field(default_factory=list)
    search_queries_used: list[str] = Field(default_factory=list)
    # 生动化扩展：人设定位 / 第一印象 / 面试官随口点评 / 同岗百分位
    # 全部可选：旧评价数据不含这些字段，前端按空缺降级
    headline: str = ""
    first_impression: str = ""
    interviewer_comments: list[str] = Field(default_factory=list)
    benchmark_percentile: int | None = Field(default=None, ge=0, le=100)


__all__ = [
    "CandidateProfile",
    "DimensionScore",
    "ResumeAnalysis",
    "ResumeResponse",
    "RewriteExample",
    "UserProfileResponse",
    "UserProfileUpdate",
]

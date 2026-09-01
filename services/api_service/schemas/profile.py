"""档案域 API 契约（候选人基本信息 CRUD）。"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


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

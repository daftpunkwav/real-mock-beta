"""候选人档案与简历选择器契约。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class CompanyInfo(BaseModel):
    id: str
    name: str
    style: str
    focus_areas: list[str]
    sample_questions: list[str]
    # 目录原始数据同时携带以下两字段；契约层补齐避免同源双视图不一致
    interview_flow: str = ""
    pressure_level: str = ""


class CandidateProfile(BaseModel):
    """结构化候选人简历档案。

    由 api_service 简历解析产出、interview 面试 Agent 读取构建候选人画像，
    两域共享，故置于 shared 契约层。
    """

    name: str = ""
    education: list[dict[str, Any]] = Field(default_factory=list)
    work_experience: list[dict[str, Any]] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    projects: list[dict[str, Any]] = Field(default_factory=list)
    summary: str = ""


class ResumePickerItem(BaseModel):
    """简历下拉只读摘要：prep / interview 配置页共用，不含解析正文与深度评价。"""

    id: int
    filename: str
    is_active: bool = False
    score: int | None = None

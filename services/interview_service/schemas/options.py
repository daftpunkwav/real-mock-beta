"""面试配置页选项与目录契约。"""

from __future__ import annotations

from pydantic import BaseModel, Field

from shared.schemas import CompanyInfo


class WorkflowTypeOption(BaseModel):
    id: str
    name: str
    phases: list[str] = Field(default_factory=list)


class OptionsResponse(BaseModel):
    roles: list[str]
    levels: list[str]
    experience_years: list[str]
    companies: list[CompanyInfo]
    personalities: list[dict[str, str]]
    interview_styles: list[dict[str, str]]
    workflow_types: list[WorkflowTypeOption]
    phase_labels: dict[str, str] = Field(default_factory=dict)
    avatars: list[dict[str, str]] = Field(default_factory=list)
    scenes: list[dict[str, str]] = Field(default_factory=list)
    tts_voices: list[dict[str, str]] = Field(default_factory=list)
    silence_nudge_seconds: int = 25

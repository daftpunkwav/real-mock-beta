"""面试报告与评分契约。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ScoreBreakdown(BaseModel):
    technical: int = 0
    communication: int = 0
    project_depth: int = 0
    problem_solving: int = 0
    presence: int = 0
    politeness: int = 0
    overall: int = 0


class InterviewReport(BaseModel):
    overall_score: int
    score_breakdown: ScoreBreakdown
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    improvement_suggestions: list[str] = Field(default_factory=list)
    resume_suggestions: list[str] = Field(default_factory=list)
    interview_suggestions: list[str] = Field(default_factory=list)
    training_plan: list[str] = Field(default_factory=list)
    phase_summary: dict[str, str] = Field(default_factory=dict)
    face_analysis_summary: str = ""
    presence_moments: list[str] = Field(default_factory=list)


class InterviewReportResponse(BaseModel):
    session_id: int
    report: InterviewReport
    messages_count: int
    duration_minutes: float | None = None

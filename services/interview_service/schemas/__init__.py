"""模拟面试域契约：面试 / 报告 / 成长 / 岗位选项。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from interview_service.constants import DEFAULT_INTERVIEW_STYLE, DEFAULT_PERSONALITY
from shared.core.constants import MAX_CONFIG_STR_CHARS, MAX_USER_TEXT_CHARS
from shared.schemas import CompanyInfo, ResumePickerItem


# ── 面试配置 ──────────────────────────────────────────


class AiOverrides(BaseModel):
    """模拟面试的处理器选择：思考 / 语音输入 / 语音输出 + 思考强度。"""

    chat_profile_id: int | None = None
    stt_profile_id: int | None = None
    tts_profile_id: int | None = None
    reasoning_effort: Literal["low", "medium", "high", "max"] | None = None

class InterviewConfig(BaseModel):
    role: str = Field(..., max_length=MAX_CONFIG_STR_CHARS)
    level: str = Field(..., max_length=MAX_CONFIG_STR_CHARS)
    company: str = Field(..., max_length=MAX_CONFIG_STR_CHARS)
    workflow_type: Literal["technical", "hr", "management"] = "technical"
    personality: Literal["gentle", "professional", "pressure", "hr", "expert"] = DEFAULT_PERSONALITY.value
    strictness: int = Field(default=3, ge=1, le=10)
    interview_style: Literal["guided", "deep_dive", "continuous", "challenging"] = DEFAULT_INTERVIEW_STYLE.value
    resume_id: int | None = None
    avatar_id: str = Field(default="professional_male", max_length=MAX_CONFIG_STR_CHARS)
    scene_id: str = Field(default="meeting_room", max_length=MAX_CONFIG_STR_CHARS)
    # 场景级 AI 覆盖：三个任务各自的模型条目 + 思考强度（缺省回落任务绑定）
    ai_overrides: "AiOverrides | None" = None


class InterviewSessionResponse(BaseModel):
    id: int
    role: str
    level: str
    company: str
    workflow_type: str
    personality: str
    strictness: int
    interview_style: str
    avatar_id: str = "professional_male"
    scene_id: str = "meeting_room"
    status: str
    current_phase: str
    overall_score: int | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None
    created_at: datetime
    # 仅 create 响应填充；list/get 为 None，避免令牌反复下发
    access_token: str | None = None


class ChatMessage(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str
    timestamp: datetime | None = None


class InterviewMessageRequest(BaseModel):
    content: str = Field(..., max_length=MAX_USER_TEXT_CHARS)
    face_analysis: dict[str, Any] | None = None
    # 当前视频帧 JPEG base64，供多模态 LLM 分析表情与状态
    # 上限约 200KB 原始数据（base64 编码后约 267KB），防止大图消耗过多 token
    image_base64: str | None = Field(default=None, max_length=300_000)


class InterviewMessageResponse(BaseModel):
    session_id: int
    message: ChatMessage
    current_phase: str
    is_complete: bool = False
    phases_remaining: list[str] = Field(default_factory=list)


# ── 报告 ──────────────────────────────────────────

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


# ── 岗位选项 ──────────────────────────────────────────

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


__all__ = [
    "ChatMessage",
    "InterviewConfig",
    "ResumePickerItem",
    "InterviewMessageRequest",
    "InterviewMessageResponse",
    "InterviewReport",
    "InterviewReportResponse",
    "InterviewSessionResponse",
    "OptionsResponse",
    "ScoreBreakdown",
    "WorkflowTypeOption",
]

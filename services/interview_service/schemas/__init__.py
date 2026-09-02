"""模拟面试域契约：按子域分文件，本包统一 re-export。

布局约定见 ``docs/package-layout.md``。
"""

from __future__ import annotations

from shared.schemas import CompanyInfo, ResumePickerItem

from .options import OptionsResponse, WorkflowTypeOption
from .report import InterviewReport, InterviewReportResponse, ScoreBreakdown
from .session import (
    AiOverrides,
    ChatMessage,
    FinishInterviewResponse,
    InterviewConfig,
    InterviewMessageRequest,
    InterviewMessageResponse,
    InterviewSessionResponse,
)

__all__ = [
    "AiOverrides",
    "ChatMessage",
    "CompanyInfo",
    "InterviewConfig",
    "ResumePickerItem",
    "InterviewMessageRequest",
    "InterviewMessageResponse",
    "FinishInterviewResponse",
    "InterviewReport",
    "InterviewReportResponse",
    "InterviewSessionResponse",
    "OptionsResponse",
    "ScoreBreakdown",
    "WorkflowTypeOption",
]

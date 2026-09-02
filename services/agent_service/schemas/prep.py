"""面试准备（Prep）HTTP 契约。"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from shared.core.constants import MAX_USER_TEXT_CHARS


class PrepCreateRequest(BaseModel):
    resume_id: int | None = None
    target_role: str = ""
    target_company: str = ""


class PrepSessionCreateResponse(BaseModel):
    id: int


class PrepSessionSummary(BaseModel):
    id: int
    resume_id: int | None = None
    resume_filename: str | None = None
    summary: str = ""
    message_count: int = 0
    status: str = "active"
    token_usage: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cached_tokens: int = 0
    created_at: datetime
    updated_at: datetime


class PrepToolStep(BaseModel):
    name: str = ""
    query: str = ""


class PrepSearchHit(BaseModel):
    title: str = ""
    url: str = ""
    snippet: str = ""


class PrepSearchGroup(BaseModel):
    query: str = ""
    results: list[PrepSearchHit] = Field(default_factory=list)


class PrepHistoryMessage(BaseModel):
    role: str
    content: str
    steps: list[PrepToolStep] | None = None
    search_groups: list[PrepSearchGroup] | None = None
    thinking: str | None = None


class PrepMessageRequest(BaseModel):
    content: str = Field(..., max_length=MAX_USER_TEXT_CHARS)
    model_profile_id: int | None = None
    reasoning_effort: str | None = Field(default=None, pattern="^(low|medium|high|max)$")


class PrepMessageResponse(BaseModel):
    reply: str
    token_usage: int = 0

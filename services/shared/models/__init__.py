"""共享数据域模型（api.db）。

- StageConfig / LLMSettings：跨服务共享的处理器配置表，已提取到
  ``shared.core.config_models``，此处 re-export 保持兼容。
- Resume / UserProfile：存于 api.db；**写**权归 ``api_service``（上传/解析/档案 CRUD）。
  agent / interview **读**须经 ``shared.services.candidate_read``（见 ``docs/shared-db-read-contract.md``）。

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from shared.database import ApiBase
from shared.models.rate_limit_bucket import RateLimitBucket
from shared.core.config_models import (  # noqa: F401  # re-export
    LLMSettings,
    LlmProvider,
    ModelProfile,
    StageConfig,
    TaskBinding,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Resume(ApiBase):
    """上传的简历及解析结果。"""

    __tablename__ = "resumes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    profile_id: Mapped[int] = mapped_column(Integer, default=1)
    filename: Mapped[str] = mapped_column(String(255))
    file_type: Mapped[str] = mapped_column(String(20))
    raw_text: Mapped[str] = mapped_column(Text, default="")
    parsed_profile: Mapped[str] = mapped_column(Text, default="{}")
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    analysis: Mapped[str] = mapped_column(Text, default="{}")  # 评分建议 JSON
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class UserProfile(ApiBase):
    """本地用户档案（候选人核心数据，api.db；写权 api_service）。"""

    __tablename__ = "user_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), default="求职者")
    gender: Mapped[str] = mapped_column(String(20), default="")
    identity: Mapped[str] = mapped_column(String(50), default="")  # 学生/在职/待业
    school: Mapped[str] = mapped_column(String(200), default="")
    major: Mapped[str] = mapped_column(String(100), default="")
    graduation_year: Mapped[str] = mapped_column(String(20), default="")
    job_direction: Mapped[str] = mapped_column(String(100), default="")
    experience_years: Mapped[str] = mapped_column(String(50), default="")
    work_years_detail: Mapped[str] = mapped_column(String(100), default="")
    current_company: Mapped[str] = mapped_column(String(200), default="")
    expected_salary: Mapped[str] = mapped_column(String(100), default="")
    self_intro: Mapped[str] = mapped_column(Text, default="")
    tech_domains: Mapped[str] = mapped_column(Text, default="[]")
    target_role: Mapped[str] = mapped_column(String(100), default="")
    # 扩展字段：供 Agent 获取更丰富候选人上下文
    github_username: Mapped[str] = mapped_column(String(100), default="")
    portfolio_url: Mapped[str] = mapped_column(String(500), default="")
    linkedin_url: Mapped[str] = mapped_column(String(500), default="")
    city: Mapped[str] = mapped_column(String(100), default="")
    preferred_languages: Mapped[str] = mapped_column(String(200), default="")  # 如 中文,English
    career_highlights: Mapped[str] = mapped_column(Text, default="")
    open_to_remote: Mapped[str] = mapped_column(String(20), default="")  # yes/no/hybrid
    notice_period: Mapped[str] = mapped_column(String(50), default="")
    # 面试常用扩展字段
    education_level: Mapped[str] = mapped_column(String(50), default="")  # 本科/硕士/博士等
    expected_city: Mapped[str] = mapped_column(String(100), default="")
    email: Mapped[str] = mapped_column(String(200), default="")
    phone: Mapped[str] = mapped_column(String(100), default="")  # 电话或微信
    certificates: Mapped[str] = mapped_column(Text, default="")
    english_level: Mapped[str] = mapped_column(String(100), default="")
    signature_projects: Mapped[str] = mapped_column(Text, default="")
    strengths: Mapped[str] = mapped_column(Text, default="")
    weaknesses: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)

    @property
    def tech_domains_list(self) -> list[str]:
        import json

        try:
            return json.loads(self.tech_domains)
        except (json.JSONDecodeError, TypeError):
            return []

    def set_tech_domains(self, domains: list[str]) -> None:
        import json

        self.tech_domains = json.dumps(domains, ensure_ascii=False)


__all__ = [
    "LLMSettings",
    "LlmProvider",
    "ModelProfile",
    "RateLimitBucket",
    "Resume",
    "StageConfig",
    "TaskBinding",
    "UserProfile",
]

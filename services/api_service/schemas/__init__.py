"""基础 API 服务契约：按业务子域分文件，本包统一 re-export。

布局约定见 ``docs/package-layout.md``。
"""

from __future__ import annotations

from shared.schemas import CandidateProfile  # noqa: F401  # 共享档案契约 re-export

from .profile import UserProfileResponse, UserProfileUpdate
from .resume import (
    CareerAnalysis,
    CompanyFit,
    DimensionScore,
    ProjectCard,
    ResumeAnalysis,
    ResumeResponse,
    RewriteExample,
    SectionReview,
    SkillTrust,
)

__all__ = [
    "CandidateProfile",
    "CompanyFit",
    "CareerAnalysis",
    "DimensionScore",
    "ProjectCard",
    "ResumeAnalysis",
    "ResumeResponse",
    "RewriteExample",
    "SectionReview",
    "SkillTrust",
    "UserProfileResponse",
    "UserProfileUpdate",
]

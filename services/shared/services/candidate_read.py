"""候选人档案 / 简历只读门面。

业务服务（agent / interview）读取 ``UserProfile`` / ``Resume`` 须经本模块，
避免各域直接 ``from shared.models import …`` 散落耦合。
写路径仍归属 ``api_service``（上传/解析）或显式写服务。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy.orm import Session

from shared.schemas import CandidateProfile

logger = logging.getLogger(__name__)

# Prep 档案摘要字段（与 prep context 对齐）
_PROFILE_SUMMARY_FIELDS: list[tuple[str, str]] = [
    ("name", "姓名"),
    ("identity", "身份"),
    ("school", "学校"),
    ("major", "专业"),
    ("education_level", "学历"),
    ("graduation_year", "毕业年份"),
    ("job_direction", "求职方向"),
    ("target_role", "目标岗位"),
    ("experience_years", "工作年限"),
    ("current_company", "当前公司"),
    ("tech_domains", "技术栈"),
    ("strengths", "自评优势"),
    ("weaknesses", "自评短板"),
    ("career_highlights", "亮点经历"),
    ("signature_projects", "代表项目"),
    ("certificates", "证书"),
    ("english_level", "英语水平"),
    ("expected_city", "期望城市"),
]


def get_user_profile(db: Session, profile_id: int) -> Any | None:
    """按 id 读取用户档案 ORM（仅供需要全字段的提示词构建）。"""
    from shared.models import UserProfile

    return db.query(UserProfile).filter(UserProfile.id == profile_id).first()


def get_default_user_profile(db: Session) -> Any | None:
    """读取默认档案：优先 id=1，否则第一条。"""
    from shared.models import UserProfile

    row = db.query(UserProfile).filter(UserProfile.id == 1).first()
    if row is None:
        row = db.query(UserProfile).first()
    return row


def format_profile_summary(db: Session, profile_id: int | None = None) -> str:
    """档案摘要文本（Prep / 提示词注入）。"""
    profile = (
        get_user_profile(db, profile_id)
        if profile_id is not None
        else get_default_user_profile(db)
    )
    if profile is None:
        return ""
    lines: list[str] = []
    for key, label in _PROFILE_SUMMARY_FIELDS:
        value = getattr(profile, key, "")
        if key == "tech_domains":
            domains = profile.tech_domains_list
            value = "、".join(domains) if domains else ""
        value = str(value or "").strip()
        if value:
            lines.append(f"{label}：{value[:80]}")
    if not lines:
        return ""
    return "求职者档案：\n" + "\n".join(lines[:18])


def format_resume_summary(db: Session, resume_id: int | None, *, max_chars: int = 3000) -> str:
    """简历文件名 + 解析 JSON 摘要。"""
    if not resume_id:
        return ""
    from shared.models import Resume

    row = db.query(Resume).filter(Resume.id == resume_id).first()
    if not row:
        return ""
    body = (row.parsed_profile or "")[:max_chars]
    return f"简历：{row.filename}\n{body}"


def get_candidate_profile(db: Session, resume_id: int | None) -> CandidateProfile | None:
    """从简历解析 JSON 构造 ``CandidateProfile``。"""
    if not resume_id:
        return None
    from shared.models import Resume

    row = db.query(Resume).filter(Resume.id == resume_id).first()
    if not row:
        return None
    try:
        return CandidateProfile(**json.loads(row.parsed_profile or "{}"))
    except (json.JSONDecodeError, TypeError, ValueError):
        logger.debug("简历 parsed_profile JSON 无效 resume_id=%s", resume_id)
        return None


def get_resume_detail(db: Session, resume_id: int) -> tuple[str, dict[str, Any]] | None:
    """返回 (filename, parsed_profile dict)。"""
    from shared.models import Resume

    row = db.query(Resume).filter(Resume.id == resume_id).first()
    if not row:
        return None
    try:
        payload = json.loads(row.parsed_profile or "{}")
        if not isinstance(payload, dict):
            payload = {}
    except (json.JSONDecodeError, TypeError):
        payload = {}
    return row.filename, payload


__all__ = [
    "format_profile_summary",
    "format_resume_summary",
    "get_candidate_profile",
    "get_default_user_profile",
    "get_resume_detail",
    "get_user_profile",
]

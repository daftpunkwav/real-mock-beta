"""简历下拉摘要：prep / interview 配置页共用的只读列表。"""

from __future__ import annotations

from sqlalchemy.orm import Session

from shared.models import Resume
from shared.schemas import ResumePickerItem


def list_resume_picker_items(db: Session) -> list[ResumePickerItem]:
    """返回简历 id / 文件名 / 激活态 / 分数，不含解析正文与深度评价。"""
    rows = db.query(Resume).order_by(Resume.created_at.desc()).all()
    return [
        ResumePickerItem(
            id=r.id,
            filename=r.filename,
            is_active=bool(r.is_active),
            score=r.score,
        )
        for r in rows
    ]

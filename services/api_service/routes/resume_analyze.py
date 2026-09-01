"""简历深度评价路由 handler。

检索词规划 / LLM 评价 / 结果规范化在
``api_service.services.resume.analysis``，本文件只保留路由薄入口。
"""

from __future__ import annotations

from fastapi import Depends
from sqlalchemy.orm import Session

from shared.models import Resume
from api_service.services.resume.analysis import analyze_resume_with_llm
from shared.core.errors import raise_error
from shared.database import get_db


async def analyze_resume(resume_id: int, db: Session = Depends(get_db)):
    r = db.query(Resume).filter(Resume.id == resume_id).first()
    if not r:
        raise_error("A1005")
    return await analyze_resume_with_llm(r, db)

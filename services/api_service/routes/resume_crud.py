"""简历 CRUD 路由 handler：列表 / 详情 / 激活 / 删除（含本地文件清理）。

本文件只定义 handler，由 ``resume.py`` 统一挂到 ``router``。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from fastapi import Depends
from sqlalchemy.orm import Session

from api_service.models import Resume
from api_service.schemas import ResumeResponse
from shared.config import get_settings
from shared.core.errors import raise_error
from shared.core.security import assert_within_dir, sanitize_filename
from shared.database import get_db
from shared.schemas import CandidateProfile

logger = logging.getLogger(__name__)
settings = get_settings()


def list_resumes(db: Session = Depends(get_db)):
    resumes = db.query(Resume).order_by(Resume.created_at.desc()).all()
    result: list[ResumeResponse] = []
    for r in resumes:
        try:
            profile = CandidateProfile(**json.loads(r.parsed_profile))
        except Exception as e:
            # 单条简历解析 JSON 损坏时降级为空 profile 但要记录,便于后续人工修复
            logger.warning("简历解析 JSON 损坏: id=%s err=%s", r.id, e)
            profile = CandidateProfile()
        result.append(
            ResumeResponse(
                id=r.id,
                filename=r.filename,
                file_type=r.file_type,
                parsed_profile=profile,
                is_active=bool(r.is_active),
                score=r.score,
                analysis=json.loads(r.analysis or "{}"),
                created_at=r.created_at,
            )
        )
    return result


def get_resume(resume_id: int, db: Session = Depends(get_db)):
    r = db.query(Resume).filter(Resume.id == resume_id).first()
    if not r:
        raise_error("A1005")
    profile = CandidateProfile(**json.loads(r.parsed_profile))
    return ResumeResponse(
        id=r.id,
        filename=r.filename,
        file_type=r.file_type,
        parsed_profile=profile,
        is_active=bool(r.is_active),
        score=r.score,
        analysis=json.loads(r.analysis or "{}"),
        created_at=r.created_at,
    )


def activate_resume(resume_id: int, db: Session = Depends(get_db)):
    # 使用行锁防止并发竞态
    r = db.query(Resume).filter(Resume.id == resume_id).with_for_update().first()
    if not r:
        raise_error("A1005")
    # 先取消其他活跃简历
    db.query(Resume).filter(Resume.id != resume_id, Resume.is_active.is_(True)).update(
        {Resume.is_active: False}, synchronize_session=False
    )
    r.is_active = True
    db.commit()
    db.refresh(r)
    return ResumeResponse(
        id=r.id,
        filename=r.filename,
        file_type=r.file_type,
        parsed_profile=CandidateProfile(**json.loads(r.parsed_profile)),
        is_active=bool(r.is_active),
        score=r.score,
        analysis=json.loads(r.analysis or "{}"),
        created_at=r.created_at,
    )


def delete_resume(resume_id: int, db: Session = Depends(get_db)):
    """删除简历及本地文件（若存在）。"""
    r = db.query(Resume).filter(Resume.id == resume_id).first()
    if not r:
        raise_error("A1005")
    # 尝试删除上传文件（文件名含 uuid 前缀，与落盘规则一致时）
    try:
        upload_dir = Path(settings.upload_dir).resolve()
        for p in upload_dir.glob(f"*_{sanitize_filename(r.filename)}"):
            try:
                assert_within_dir(p, upload_dir)
                p.unlink(missing_ok=True)
            except Exception:
                pass
    except Exception as e:
        logger.warning("删除简历文件时忽略错误: %s", e)
    db.delete(r)
    db.commit()
    return {"ok": True, "id": resume_id}

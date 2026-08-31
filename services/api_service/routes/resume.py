"""简历上传与解析 API。

安全要点（已加固）：

- 上传大小上限 :data:`shared.core.constants.RESUME_MAX_UPLOAD_BYTES`（默认 10 MB）；
- 文件名走 :func:`shared.core.security.sanitize_filename` 清洗，落盘后
  :func:`shared.core.security.assert_within_dir` 再做越界校验；
- 通过魔数嗅探真实 MIME，不依赖客户端 ``content_type``；
- LLM 返回的结构化 JSON 经 ``ResumeAnalysis`` 强校验（防御 Pydantic-v2
  ``extra="forbid"`` 之外的 Prompt 注入）。

深度评价（检索词规划 / LLM 评价 / 结果规范化）见
``api_service.services.resume.analysis``，本文件只保留上传与 CRUD 路由。
"""

import json
import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.orm import Session

from shared.config import get_settings
from shared.core.errors import raise_error
from shared.core.local_only import require_local_peer
from shared.core.constants import (
    DEFAULT_LLM_RATE_LIMIT_PER_MINUTE,
    DEFAULT_RATE_LIMIT_PER_MINUTE,
    RESUME_ALLOWED_EXTENSIONS,
    RESUME_MAX_UPLOAD_BYTES,
)
from shared.core.ratelimit import rate_limit_dep
from shared.core.security import (
    assert_within_dir,
    sanitize_filename,
)
from shared.database import get_db
from api_service.models import Resume
from shared.schemas import CandidateProfile
from api_service.schemas import ResumeAnalysis, ResumeResponse
from api_service.services.resume.parser import extract_text_from_file, parse_resume_with_llm
from api_service.services.resume.analysis import analyze_resume_with_llm
from shared.capabilities.ai.llm.client import LLMClient

router = APIRouter(dependencies=[Depends(require_local_peer)])
logger = logging.getLogger(__name__)
settings = get_settings()

ALLOWED_EXTENSIONS = RESUME_ALLOWED_EXTENSIONS  # 兼容旧引用

# 扩展名 ↔ 魔数（仅做基础嗅探）
_MAGIC_BYTES: dict[str, list[bytes]] = {
    "pdf": [b"%PDF-"],
    "docx": [b"PK\x03\x04"],  # zip 容器
    "doc": [b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"],  # OLE
}


def _sniff_extension(head: bytes, ext: str) -> bool:
    """基于文件头校验扩展名真实性。"""
    sigs = _MAGIC_BYTES.get(ext)
    if not sigs:
        return True  # md / txt 等纯文本不强校验
    return any(head.startswith(sig) for sig in sigs)


@router.post(
    "/upload",
    response_model=ResumeResponse,
    dependencies=[
        Depends(
            rate_limit_dep(
                key="upload",
                limit=DEFAULT_RATE_LIMIT_PER_MINUTE,
            )
        )
    ],
)
async def upload_resume(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    filename = (file.filename or "").strip()
    if not filename:
        raise_error("A1001")

    ext = filename.rsplit(".", 1)[-1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise_error("A1002", exts=", ".join(ALLOWED_EXTENSIONS))

    upload_dir = Path(settings.upload_dir).resolve()
    upload_dir.mkdir(parents=True, exist_ok=True)

    # 流式读取并按上限截断，超过立即拒绝
    total = 0
    chunks: list[bytes] = []
    while chunk := await file.read(64 * 1024):
        total += len(chunk)
        if total > RESUME_MAX_UPLOAD_BYTES:
            raise_error("A0413", max=RESUME_MAX_UPLOAD_BYTES // (1024 * 1024))
        chunks.append(chunk)
    content = b"".join(chunks)

    if total == 0:
        raise_error("A0005")

    # 校验扩展名真实（防止扩展名伪造）
    if not _sniff_extension(content[:8], ext):
        raise_error("A1003")

    # 安全文件名 + 路径穿越防护
    safe_name = f"{uuid.uuid4().hex[:8]}_{sanitize_filename(filename)}"
    file_path = assert_within_dir(Path(safe_name), upload_dir)
    file_path.write_bytes(content)

    try:
        raw_text = extract_text_from_file(file_path, ext)
    except Exception as e:
        logger.warning("简历解析失败: %s", e)
        raise_error("A1004", cause=e)

    llm = LLMClient.from_db(db)
    if llm.api_key:
        parsed = await parse_resume_with_llm(raw_text, llm)
    else:
        parsed = CandidateProfile(summary=raw_text[:500])

    resume = Resume(
        filename=filename,
        file_type=ext,
        raw_text=raw_text[:50000],
        parsed_profile=parsed.model_dump_json(),
    )
    db.add(resume)
    db.commit()
    db.refresh(resume)

    return ResumeResponse(
        id=resume.id,
        filename=resume.filename,
        file_type=resume.file_type,
        parsed_profile=parsed,
        is_active=resume.is_active,
        score=resume.score,
        analysis=json.loads(resume.analysis or "{}"),
        created_at=resume.created_at,
    )


@router.get("/list", response_model=list[ResumeResponse])
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


@router.get("/{resume_id}", response_model=ResumeResponse)
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


@router.post("/{resume_id}/activate", response_model=ResumeResponse)
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


@router.delete("/{resume_id}")
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


@router.post(
    "/{resume_id}/analyze",
    response_model=ResumeAnalysis,
    dependencies=[
        Depends(
            rate_limit_dep(
                key="llm",
                limit=DEFAULT_LLM_RATE_LIMIT_PER_MINUTE,
            )
        )
    ],
)
async def analyze_resume(resume_id: int, db: Session = Depends(get_db)):
    r = db.query(Resume).filter(Resume.id == resume_id).first()
    if not r:
        raise_error("A1005")
    return await analyze_resume_with_llm(r, db)

"""简历上传路由 handler：大小上限 / 扩展名白名单 / 魔数嗅探 / 路径穿越防护。

安全要点：

- 上传大小上限 :data:`shared.core.constants.RESUME_MAX_UPLOAD_BYTES`（默认 10 MB）；
- 文件名走 :func:`shared.core.security.sanitize_filename` 清洗，落盘后
  :func:`shared.core.security.assert_within_dir` 再做越界校验；
- 通过魔数嗅探真实 MIME，不依赖客户端 ``content_type``；
- LLM 返回的结构化 JSON 经 ``ResumeAnalysis`` 强校验（防御 Pydantic-v2
  ``extra="forbid"`` 之外的 Prompt 注入）。

本文件只定义 handler，由 ``resume.py`` 统一挂到 ``router``。
"""

from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path

from fastapi import Depends, File, UploadFile
from sqlalchemy.orm import Session

from shared.models import Resume
from api_service.schemas import ResumeResponse
from api_service.services.resume.parser import extract_text_from_file, parse_resume_with_llm
from shared.capabilities.ai.llm.client import LLMClient
from shared.config import get_settings
from shared.core.constants import RESUME_ALLOWED_EXTENSIONS, RESUME_MAX_UPLOAD_BYTES
from shared.core.errors import raise_error
from shared.core.security import assert_within_dir, sanitize_filename
from shared.database import get_db
from shared.schemas import CandidateProfile

logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = RESUME_ALLOWED_EXTENSIONS

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

    upload_dir = Path(get_settings().upload_dir).resolve()
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

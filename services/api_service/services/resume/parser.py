"""简历文本提取与 AI 解析。"""

from __future__ import annotations

import logging
import zipfile
from pathlib import Path

from docx import Document
from pypdf import PdfReader

from shared.core.prompts import with_agent_output_rules
from shared.schemas import CandidateProfile
from shared.capabilities.ai.llm.client import LLMClient

logger = logging.getLogger(__name__)

# 解析资源上限，缓解压缩炸弹 / 超大文档 DoS
_MAX_PDF_PAGES = 50
_MAX_DOCX_ZIP_ENTRIES = 200
_MAX_DOCX_UNCOMPRESSED_BYTES = 30 * 1024 * 1024
_MAX_EXTRACTED_CHARS = 100_000
_MAX_PARAGRAPHS = 5_000

PARSE_SYSTEM_PROMPT = with_agent_output_rules("""你是一位专业的简历解析专家。请从简历文本中提取结构化信息，以 JSON 格式返回。

返回格式：
{
  "name": "姓名",
  "education": [{"school": "", "degree": "", "major": "", "period": ""}],
  "work_experience": [{"company": "", "title": "", "period": "", "description": ""}],
  "skills": ["技能1", "技能2"],
  "projects": [{"name": "", "role": "", "tech_stack": "", "description": "", "highlights": "", "challenges": ""}],
  "summary": "一句话职业总结"
}

只返回 JSON，不要其他内容。文本字段禁止 emoji。""")


def _truncate(text: str) -> str:
    if len(text) <= _MAX_EXTRACTED_CHARS:
        return text
    return text[:_MAX_EXTRACTED_CHARS]


def _assert_docx_zip_safe(file_path: Path) -> None:
    """校验 DOCX（ZIP）条目数与解压后体积，防 zip bomb。"""
    with zipfile.ZipFile(file_path, "r") as zf:
        infos = zf.infolist()
        if len(infos) > _MAX_DOCX_ZIP_ENTRIES:
            raise ValueError(
                f"DOCX 条目过多（{len(infos)} > {_MAX_DOCX_ZIP_ENTRIES}）"
            )
        total = 0
        for info in infos:
            total += max(0, int(info.file_size))
            if total > _MAX_DOCX_UNCOMPRESSED_BYTES:
                raise ValueError("DOCX 解压后体积超过上限")


def extract_text_from_file(file_path: Path, file_type: str) -> str:
    """从 PDF/DOCX/MD/TXT 提取纯文本。"""
    suffix = file_type.lower()

    if suffix == "pdf":
        reader = PdfReader(str(file_path))
        pages = reader.pages
        if len(pages) > _MAX_PDF_PAGES:
            raise ValueError(f"PDF 页数过多（{len(pages)} > {_MAX_PDF_PAGES}）")
        text = "\n".join((page.extract_text() or "") for page in pages)
        return _truncate(text)

    if suffix in ("docx", "doc"):
        _assert_docx_zip_safe(file_path)
        doc = Document(str(file_path))
        paras = doc.paragraphs[:_MAX_PARAGRAPHS]
        text = "\n".join(p.text for p in paras)
        return _truncate(text)

    # md / txt / 其他文本格式
    raw = file_path.read_text(encoding="utf-8", errors="ignore")
    return _truncate(raw)


async def parse_resume_with_llm(
    raw_text: str,
    llm: LLMClient,
) -> CandidateProfile:
    """使用 LLM 将简历文本解析为 Candidate Profile。"""
    messages = [
        {"role": "system", "content": PARSE_SYSTEM_PROMPT},
        {"role": "user", "content": f"请解析以下简历：\n\n{raw_text[:15000]}"},
    ]
    try:
        data = await llm.chat_json(messages)
        return CandidateProfile(**data)
    except Exception as e:
        logger.warning("LLM 简历解析失败，使用基础解析: %s", e)
        return CandidateProfile(summary=raw_text[:500])

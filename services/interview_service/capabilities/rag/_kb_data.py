"""企业知识库纯数据层：无业务依赖，供 company_rag / local_backend / 测试共用。

包含：
- :data:`COLLECTION_NAME` — Chroma 集合名
- :func:`_build_documents` — 将 BUILTIN_COMPANIES 展开为 Chroma 三元组
- :func:`_data_dir` — Chroma 持久化目录
- :func:`format_context` — 检索结果格式化
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from shared.catalogs.company import BUILTIN_COMPANIES

logger = logging.getLogger(__name__)


def _data_dir() -> Path:
    """Chroma 持久化目录（与 DB 同目录，统一在 shared/data）。"""
    from shared.config import SHARED_ROOT, get_settings

    settings = get_settings()
    db_path = settings.database_url.replace("sqlite:///", "")
    if db_path and not db_path.startswith(":"):
        chroma_dir = Path(db_path).parent / "chroma"
    else:
        # 内存库等场景回退到共享数据根
        chroma_dir = SHARED_ROOT / "data" / "chroma"
    chroma_dir.mkdir(parents=True, exist_ok=True)
    return chroma_dir


COLLECTION_NAME = "company_interview_kb"


def _build_documents() -> tuple[list[str], list[dict[str, Any]], list[str]]:
    """将 BUILTIN_COMPANIES 展开为 Chroma 三元组 (texts, metadatas, ids)。"""
    texts: list[str] = []
    metadatas: list[dict[str, Any]] = []
    ids: list[str] = []

    for company in BUILTIN_COMPANIES:
        cid = company["id"]
        # 切片 1：总体风格
        texts.append(
            f"{company['name']}（{cid}）面试风格：{company['style']}。"
            f"压力等级：{company['pressure_level']}。"
        )
        metadatas.append({
            "company_id": cid,
            "company_name": company["name"],
            "section": "style",
        })
        ids.append(f"{cid}::style")

        # 切片 2：重点领域
        texts.append(
            f"{company['name']}考察重点领域：{', '.join(company['focus_areas'])}。"
        )
        metadatas.append({
            "company_id": cid,
            "company_name": company["name"],
            "section": "focus_areas",
        })
        ids.append(f"{cid}::focus_areas")

        # 切片 3：典型问题（每题一片）
        for idx, q in enumerate(company["sample_questions"]):
            texts.append(
                f"{company['name']}典型面试问题示例：{q}"
            )
            metadatas.append({
                "company_id": cid,
                "company_name": company["name"],
                "section": "sample_question",
                "question_index": idx,
            })
            ids.append(f"{cid}::q::{idx}")

        # 切片 4：面试流程
        texts.append(
            f"{company['name']}典型面试流程：{company['interview_flow']}"
        )
        metadatas.append({
            "company_id": cid,
            "company_name": company["name"],
            "section": "interview_flow",
        })
        ids.append(f"{cid}::flow")

    return texts, metadatas, ids


def format_context(hits: list[dict[str, Any]]) -> str:
    """把检索结果格式化为可注入 LLM prompt 的中文上下文片段。"""
    if not hits:
        return ""
    lines = ["## 企业知识库检索补充"]
    for i, hit in enumerate(hits, 1):
        meta = hit.get("metadata", {})
        section = meta.get("section", "")
        text = hit.get("text", "")
        lines.append(f"{i}. [{section}] {text}")
    return "\n".join(lines)


__all__ = [
    "COLLECTION_NAME",
    "_build_documents",
    "_data_dir",
    "format_context",
]

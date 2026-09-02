"""模拟面试服务启动钩子。"""

from __future__ import annotations

import logging

from shared.database import ApiSessionLocal
from bootstrap.db_bootstrap import bootstrap_databases_and_seed

logger = logging.getLogger(__name__)


def startup() -> None:
    bootstrap_databases_and_seed()


async def ensure_rag_index() -> None:
    """首次启动构建企业知识库 RAG 索引（失败不阻断启动）。"""
    import os

    if os.environ.get("TEST_MODE") == "1":
        return
    try:
        from shared.capabilities.ai.llm.client import LLMClient
        from interview_service.capabilities.rag.company_rag import CompanyKnowledgeRAG

        db = ApiSessionLocal()
        try:
            llm = LLMClient.from_db(db)
            api_key = getattr(llm, "api_key", None)
            if not api_key:
                logger.info("未配置 LLM API Key，跳过 RAG 索引构建")
                return
            rag = CompanyKnowledgeRAG(llm)
            await rag.ensure_index()
        finally:
            try:
                db.close()
            except Exception:
                logger.debug("RAG 启动 ApiSessionLocal close 失败", exc_info=True)
    except Exception as e:
        logger.warning("RAG 索引构建失败（启动继续）: %s", e)

"""模拟面试服务启动钩子。

- ``startup``：聚合建表/迁移（过渡期经 shared.init_db）+ 企业知识库 RAG
  索引构建（rag 唯一运行时消费者是本服务的面试引擎，索引归本服务拥有）。
"""

from __future__ import annotations

import logging

from shared.database import init_db, SessionLocal
from shared.core.migrate import run_migrations
from shared.database import engine

logger = logging.getLogger(__name__)


def startup() -> None:
    """同步初始化：建表 + 迁移 + 企业知识库 RAG 索引。"""
    init_db()
    run_migrations(engine)


async def ensure_rag_index() -> None:
    """首次启动构建企业知识库 RAG 索引（失败不阻断启动）。

    LLM 未配置或没有 API Key 时安全跳过。
    """
    try:
        from shared.capabilities.ai.llm.client import LLMClient
        from shared.capabilities.knowledge.rag.company_rag import CompanyKnowledgeRAG

        db = SessionLocal()
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
                pass
    except Exception as e:
        logger.warning("RAG 索引构建失败（启动继续）: %s", e)

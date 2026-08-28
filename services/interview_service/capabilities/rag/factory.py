"""RAG 后端工厂与 ``none`` 占位实现。

读取 :class:`shared.config.Settings` 的 ``rag_backend`` 字段,选择并构造对应
后端。新增后端时：实现 :class:`RAGBackend` 协议 → 在 ``build_rag_backend`` 中
加一个分支即可,无需触动调用方。
"""

from __future__ import annotations

import logging
from typing import Any

from shared.config import Settings
from shared.core.constants import RAGBackendKind
from shared.capabilities.ai.llm.client import LLMClient
from shared.capabilities.knowledge.rag.base import RAGBackend

logger = logging.getLogger(__name__)


class _NullRAG:
    """``RAGBackendKind.NONE`` 占位实现。

    所有方法均安全降级：``ensure_index`` no-op、``is_empty`` 恒 True、
    ``query`` 永返 ``[]``。便于在生产环境或调试时关闭企业知识库。
    """

    kind = RAGBackendKind.NONE

    async def ensure_index(self) -> None:  # noqa: D401
        return None

    def is_empty(self) -> bool:
        return True

    async def query(
        self,
        query_text: str,
        *,
        top_k: int = 3,
        company_id: str | None = None,
    ) -> list[dict[str, Any]]:
        return []

    async def query_for_company(
        self,
        query_text: str,
        company_id: str,
        *,
        top_k: int = 4,
    ) -> list[dict[str, Any]]:
        return []


def build_rag_backend(llm: LLMClient, settings: Settings) -> RAGBackend:
    """根据 ``settings.rag_backend`` 选择后端实现。

    Args:
        llm: BYOK LLM 客户端,后端会按需复用其凭据。
        settings: 应用配置,从中读取 ``rag_backend`` / ``stepfun_vector_store_id`` 等。

    Returns:
        任意 :class:`RAGBackend` 协议实现。
    """
    kind = settings.rag_backend

    if kind == RAGBackendKind.NONE:
        logger.info("RAG 后端 = none，企业知识库检索已关闭")
        return _NullRAG()

    if kind == RAGBackendKind.STEPFUN:
        # 延迟导入：避免 stepfun_backend 强依赖在未使用时也被加载。
        from shared.capabilities.knowledge.rag.stepfun_backend import StepFunRetrievalRAG

        logger.info("RAG 后端 = stepfun（StepFun 托管 vector_stores）")
        return StepFunRetrievalRAG(llm=llm, settings=settings)

    # 默认：本地 Chroma + OpenAI 兼容 /embeddings
    from shared.capabilities.knowledge.rag.local_backend import LocalEmbeddingRAG

    logger.info("RAG 后端 = local（本地 Chroma + /embeddings）")
    return LocalEmbeddingRAG(llm=llm, settings=settings)


__all__ = ["build_rag_backend"]
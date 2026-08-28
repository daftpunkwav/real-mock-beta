"""企业面试知识库 RAG。

构造时按 settings.rag_backend 选择后端实现(local Chroma / stepfun / none);
llm=None 时降级为空 stub(测试场景)。显式委托方法,无 __getattr__ 魔法。

纯数据/工具函数(_build_documents / _data_dir / format_context / COLLECTION_NAME)
在 :mod:`shared.capabilities.knowledge.rag._kb_data`。
"""

from __future__ import annotations

import logging
from typing import Any

from shared.capabilities.knowledge.rag._kb_data import COLLECTION_NAME, _build_documents, _data_dir, format_context
from shared.capabilities.knowledge.rag.factory import build_rag_backend

logger = logging.getLogger(__name__)


class _LegacyChromaStub:
    """``CompanyKnowledgeRAG(llm=None)`` 用的最小占位实现(测试场景)。"""

    kind = None  # type: ignore[assignment]
    _llm = None
    _client = None
    _collection = None

    async def ensure_index(self) -> None:
        return None

    def is_empty(self) -> bool:
        if self._collection is None:
            return True
        return self._collection.count() == 0

    async def query(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        return []

    async def query_for_company(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        return []


class CompanyKnowledgeRAG:
    """企业知识库 RAG(按 settings 选择后端,显式委托)。

    公开方法 ensure_index / is_empty / query / query_for_company 委托给
    工厂选出的后端;llm=None 时降级为 _LegacyChromaStub。
    """

    def __init__(self, llm: Any = None) -> None:
        if llm is None:
            self._impl: Any = _LegacyChromaStub()
        else:
            from shared.config import get_settings

            self._impl = build_rag_backend(llm=llm, settings=get_settings())

    @property
    def kind(self) -> Any:
        return self._impl.kind

    async def ensure_index(self) -> None:
        await self._impl.ensure_index()

    def is_empty(self) -> bool:
        return self._impl.is_empty()

    async def query(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        return await self._impl.query(*args, **kwargs)

    async def query_for_company(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        return await self._impl.query_for_company(*args, **kwargs)


__all__ = [
    "CompanyKnowledgeRAG",
    "COLLECTION_NAME",
    "format_context",
    "_build_documents",
    "_data_dir",
]

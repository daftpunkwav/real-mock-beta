"""RAG 后端抽象接口。

设计目标：不同 LLM 服务商实现各自的检索协议时,只需实现 :class:`RAGBackend`
协议即可被上层（:class:`app.services.interview.runner.InterviewRunner` 等）无差别使用。

当前已实现后端（见同目录各 ``*_backend.py``）：

- :class:`LocalEmbeddingRAG` — 本地 Chroma + OpenAI 兼容 ``/embeddings``；
- :class:`StepFunRetrievalRAG` — StepFun 托管 vector_stores,检索走
  ``tools[].type=retrieval``。

新增后端的契约：

- 必须声明 :attr:`kind` 用于日志与工厂选择；
- :meth:`query` 返回 ``list[dict]``，元素至少包含 ``text`` / ``metadata`` / ``distance``；
- 检索不可用时必须返回空列表而非抛异常(沿用现有 CompanyKnowledgeRAG 行为)。
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from shared.core.constants import RAGBackendKind


@runtime_checkable
class RAGBackend(Protocol):
    """RAG 后端统一接口。

    所有方法在出错时倾向降级（返回空列表 / 内部 warn）而非抛出,以保持
    启动与面试主流程的鲁棒性。具体的失败策略由各实现自行决定。
    """

    kind: RAGBackendKind

    async def ensure_index(self) -> None:
        """确保索引就绪。空库场景下尝试构建,失败仅 warn。"""
        ...

    def is_empty(self) -> bool:
        """索引是否为空。空时上层会跳过检索。"""
        ...

    async def query(
        self,
        query_text: str,
        *,
        top_k: int = 3,
        company_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """检索与查询最相关的文档片段。

        Returns:
            元素包含 ``text`` / ``metadata`` / ``distance`` 的字典列表;
            不可用时返回 ``[]``。
        """
        ...

    async def query_for_company(
        self,
        query_text: str,
        company_id: str,
        *,
        top_k: int = 4,
    ) -> list[dict[str, Any]]:
        """限定公司检索。"""
        ...


__all__ = ["RAGBackend"]
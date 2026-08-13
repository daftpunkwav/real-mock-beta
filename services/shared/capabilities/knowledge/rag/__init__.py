"""RAG 子模块聚合导出。

外部引用统一走这里，避免在多处直接 import 内部文件路径：

- :class:`RAGBackend` —— 后端协议
- :func:`build_rag_backend` —— 后端工厂
- :class:`CompanyKnowledgeRAG` —— 向后兼容包装器（保留旧 API）
- :func:`format_context` —— 命中片段 → 中文上下文片段（与具体后端无关）
"""

from shared.capabilities.knowledge.rag.base import RAGBackend
from shared.capabilities.knowledge.rag.company_rag import (
    COLLECTION_NAME,
    CompanyKnowledgeRAG,
    format_context,
)
from shared.capabilities.knowledge.rag.factory import build_rag_backend

__all__ = [
    "RAGBackend",
    "build_rag_backend",
    "CompanyKnowledgeRAG",
    "format_context",
    "COLLECTION_NAME",
]
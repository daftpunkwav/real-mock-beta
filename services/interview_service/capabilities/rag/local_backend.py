"""本地 Chroma + OpenAI 兼容 ``/embeddings`` 的 RAG 后端。

适用场景：所有暴露 OpenAI 兼容 ``/embeddings`` 接口的 LLM 服务商
（OpenAI / DeepSeek / SiliconFlow / Moonshot / GLM / 阿里云百炼等）。

实现要点：

- 持久化目录 ``services/shared/data/chroma``（与
  :data:`interview_service.capabilities.rag.company_rag.COLLECTION_NAME` 一致）；
- 文档切片策略沿用 :func:`interview_service.capabilities.rag.company_rag._build_documents`；
- 嵌入调用走 :meth:`shared.capabilities.ai.llm.client.LLMClient.embed`,
  后者已支持独立 ``LLM_EMBEDDINGS_*`` 配置。
"""

from __future__ import annotations

import logging
from typing import Any

from shared.config import Settings
from shared.core.constants import RAGBackendKind
from interview_service.capabilities.rag._kb_data import COLLECTION_NAME, _build_documents, _data_dir
from shared.capabilities.ai.llm.client import LLMClient

logger = logging.getLogger(__name__)


class LocalEmbeddingRAG:
    """本地向量库 + 远端 embedding 的标准 RAG 实现。"""

    kind = RAGBackendKind.LOCAL

    def __init__(self, llm: LLMClient | None = None, settings: Settings | None = None):
        # ``chromadb`` 在 import 期较重,延迟到首次实例化。
        import chromadb
        from chromadb.config import Settings as ChromaSettings

        self._llm = llm
        self._settings = settings
        self._client = chromadb.PersistentClient(
            path=str(_data_dir()),
            settings=ChromaSettings(anonymized_telemetry=False, allow_reset=True),
        )
        self._collection = self._client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )

    def is_empty(self) -> bool:
        return self._collection.count() == 0

    async def build_index(self, force: bool = False) -> int:
        """构建（首次）或重建索引。供 :meth:`ensure_index` 与测试调用。"""
        if force and self._collection.count() > 0:
            self._delete_all()
        if self._collection.count() > 0:
            logger.info("Local RAG 索引已存在，跳过构建")
            return self._collection.count()
        if self._llm is None:
            raise RuntimeError("首次构建 Local RAG 索引需要提供 LLMClient 用于 embed()")

        texts, metadatas, ids = _build_documents()
        logger.info("构建 Local RAG 索引：%d 条文档", len(texts))
        embeddings = await self._llm.embed(texts)
        # chromadb 类型标注对 add 的参数较严格，运行时兼容列表输入
        self._collection.add(
            documents=texts,
            embeddings=embeddings,  # type: ignore[arg-type]
            metadatas=metadatas,  # type: ignore[arg-type]
            ids=ids,
        )
        return len(texts)

    async def ensure_index(self) -> None:
        if self.is_empty():
            try:
                await self.build_index(force=False)
            except Exception as e:
                logger.warning("Local RAG 索引构建失败，将保持空状态: %s", e)

    async def query(
        self,
        query_text: str,
        *,
        top_k: int = 3,
        company_id: str | None = None,
    ) -> list[dict[str, Any]]:
        if self._collection.count() == 0:
            logger.warning("Local RAG 索引为空，跳过检索")
            return []
        if self._llm is None:
            raise RuntimeError("Local RAG 检索需要 LLMClient 用于 query embedding")

        query_emb = (await self._llm.embed([query_text]))[0]
        kwargs: dict[str, Any] = {
            "query_embeddings": [query_emb],
            "n_results": top_k,
        }
        if company_id:
            kwargs["where"] = {"company_id": company_id}

        result = self._collection.query(**kwargs)
        # chromadb 返回值为 list[list[...]] 包裹；兼容 None（缺省分支）
        documents = (result.get("documents") or [[]])[0] or []
        metadatas = (result.get("metadatas") or [[]])[0] or []
        distances = (result.get("distances") or [[]])[0] or []
        return [
            {
                "text": doc,
                "metadata": meta or {},
                "distance": dist,
            }
            for doc, meta, dist in zip(documents, metadatas, distances)
        ]

    async def query_for_company(
        self,
        query_text: str,
        company_id: str,
        *,
        top_k: int = 4,
    ) -> list[dict[str, Any]]:
        return await self.query(query_text, top_k=top_k, company_id=company_id)

    def _delete_all(self) -> None:
        try:
            self._client.delete_collection(COLLECTION_NAME)
        except Exception:
            pass
        self._collection = self._client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )


__all__ = ["LocalEmbeddingRAG"]
"""StepFun 托管 vector_stores 的 RAG 后端。

StepFun 平台不暴露 ``/embeddings`` 端点,而是把检索做成 OpenAI 协议里的
一个内置 tool 类型:

.. code-block:: python

    tools = [{
        "type": "retrieval",
        "function": {
            "name": "company_kb",
            "description": "公司面试风格知识库",
            "options": {
                "vector_store_id": "1712...",
                "prompt_template": "从文档 {{knowledge}} 中找到与 {{query}} 相关的内容;若没有则回答'无相关资料'。",
            },
        },
    }]

StepFun 服务端会在 chat 调用时自动执行检索并把相关片段塞回上下文,
因此本后端的职责是：

1. :meth:`ensure_index` —— 在 StepFun 端创建 / 复用 vector_store 并上传
   内置企业知识库文档(若用户已在 ``STEPFUN_VECTOR_STORE_ID`` 提供则跳过)；
2. :meth:`query` —— 返回空列表,真实检索由 chat 时的 tools 完成；
3. :meth:`build_retrieval_tool` —— 输出 OpenAI 兼容的 tool 定义,
   由 :class:`app.services.interview.runner.InterviewRunner` 注入到 chat payload。
"""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from shared.config import Settings
from shared.core.constants import RAGBackendKind
from shared.core.security import (
    UnsafeURLError,
    assert_safe_http_url,
    is_safe_http_url,
    make_pinned_async_client,
    redact_api_key,
)
from shared.capabilities.ai.llm.client import LLMClient
from interview_service.capabilities.rag._kb_data import _build_documents

logger = logging.getLogger(__name__)


_STEPFUN_FILE_NAME = "company_kb.jsonl"
_STEPFUN_VS_NAME = "company_kb"
_STEPFUN_REQUEST_TIMEOUT = 30.0


def _serialize_documents_to_jsonl() -> bytes:
    """把 BUILTIN_COMPANIES 切片成 StepFun 可消费的 JSONL 字节流。

    每行一个 JSON 对象,字段 ``text`` 为切片文本,``metadata`` 携带
    ``company_id`` / ``company_name`` / ``section``,便于 StepFun 服务端
    做召回时的过滤参考。
    """
    texts, metadatas, _ = _build_documents()
    lines: list[str] = []
    for text, meta in zip(texts, metadatas):
        lines.append(json.dumps({"text": text, "metadata": meta}, ensure_ascii=False))
    return ("\n".join(lines) + "\n").encode("utf-8")


class StepFunRetrievalRAG:
    """StepFun 托管 vector_stores 后端。"""

    kind = RAGBackendKind.STEPFUN

    def __init__(self, llm: LLMClient, settings: Settings):
        self._llm = llm
        self._settings = settings
        self._vector_store_id: str | None = settings.stepfun_vector_store_id
        self._ready: bool = bool(self._vector_store_id)

    # ── 公共 API ──────────────────────────────────────

    def is_empty(self) -> bool:
        """StepFun 后端没有本地索引,未就绪时返回 True 让上层跳过本地检索。

        真实检索由 chat 时 StepFun 服务端执行,与本属性无关。
        """
        return not self._ready

    async def ensure_index(self) -> None:
        """确保 StepFun 端 vector_store 已创建并关联了知识库文件。

        流程:

        1. 若 ``STEPFUN_VECTOR_STORE_ID`` 已配置 → 仅做存在性校验;
        2. 否则按官方文档流程:
           POST /vector_stores → POST /files (purpose=retrieval)
           → POST /vector_stores/{id}/files 关联;
        3. 失败一律 ``logger.warning``,不抛出(沿用现有降级策略)。
        """
        api_base = self._settings.effective_embeddings_base  # StepFun 通常与 chat 共 base
        api_key = self._llm.api_key

        if not api_key:
            logger.warning("StepFun RAG 跳过：未配置 API Key")
            return

        try:
            assert_safe_http_url(api_base, allow_local=False)
        except UnsafeURLError as e:
            logger.warning("StepFun RAG 跳过：api_base 不安全 (%s)", e)
            return

        try:
            if self._vector_store_id:
                await self._verify_vector_store(api_base, api_key, self._vector_store_id)
                self._ready = True
                logger.info(
                    "StepFun vector_store 已就绪（复用配置）: id=%s",
                    self._vector_store_id,
                )
                return

            vs_id = await self._create_vector_store(api_base, api_key)
            file_id = await self._upload_kb_file(api_base, api_key)
            await self._attach_file(api_base, api_key, vs_id, file_id)
            self._vector_store_id = vs_id
            self._ready = True
            # 注意：仅打印 ID，文件大小可观察但不视为敏感。
            logger.info(
                "StepFun vector_store 创建成功: id=%s file=%s",
                vs_id,
                file_id,
            )
        except Exception as e:
            logger.warning("StepFun RAG 索引构建失败（保持无 RAG 模式）: %s", e)
            self._ready = False

    async def query(
        self,
        query_text: str,
        *,
        top_k: int = 3,
        company_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """StepFun 后端不直接做本地检索；返回空列表。

        真实检索由 chat 调用时 StepFun 服务端通过 ``tools[].type=retrieval``
        完成。本方法仍返回 ``[]`` 以满足 :class:`RAGBackend` 协议,
        这样 :class:`InterviewRunner` 在 RAG 注入分支无需为 StepFun 单独
        判断,统一走 ``hits`` 为空的逻辑。
        """
        return []

    async def query_for_company(
        self,
        query_text: str,
        company_id: str,
        *,
        top_k: int = 4,
    ) -> list[dict[str, Any]]:
        return []

    # ── StepFun 检索协议产物 ───────────────────────────────

    def build_retrieval_tool(self) -> dict[str, Any] | None:
        """生成 OpenAI 兼容的 retrieval tool 定义。

        Returns:
            若 ``vector_store_id`` 就绪则返回 tool dict,否则返回 ``None``
            （让调用方跳过注入而非注入一个非法工具）。
        """
        if not self._ready or not self._vector_store_id:
            return None
        return {
            "type": "retrieval",
            "function": {
                "name": "company_kb",
                "description": (
                    "公司面试风格知识库。包含字节、腾讯、阿里、美团、米哈游、"
                    "OpenAI、Google 等公司的面试风格、重点领域、典型问题与流程。"
                ),
                "options": {
                    "vector_store_id": self._vector_store_id,
                    "prompt_template": (
                        "从文档 {{knowledge}} 中找到与 {{query}} 相关的内容;"
                        "若文档没有相关答案,明确告知'无相关资料'。"
                    ),
                },
            },
        }

    # ── StepFun HTTP 私有方法 ───────────────────────────────

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._llm.api_key}",
            "Content-Type": "application/json",
        }

    def _pinned_client(self, api_base: str) -> httpx.AsyncClient:
        """与 LLM client 一致：出站 DNS pin，缓解重绑定 TOCTOU。"""
        from shared.config import get_settings

        return make_pinned_async_client(
            api_base,
            allow_local=False,
            require_https=bool(get_settings().is_prod),
            timeout=_STEPFUN_REQUEST_TIMEOUT,
        )

    async def _create_vector_store(self, api_base: str, api_key: str) -> str:
        """POST /vector_stores → 返回 vector_store_id。"""
        url = f"{api_base}/vector_stores"
        # 双重 SSRF 校验：防御性编程,即便 ensure_index 已校验过。
        if not is_safe_http_url(url, allow_local=False):
            raise UnsafeURLError(f"StepFun URL 被拒: {url}")
        payload = {"name": _STEPFUN_VS_NAME}
        async with self._pinned_client(api_base) as client:
            resp = await client.post(url, headers=self._headers(), json=payload)
            if resp.status_code >= 400:
                logger.warning(
                    "StepFun create vector_store 失败: status=%s key=%s",
                    resp.status_code,
                    redact_api_key(api_key),
                )
            resp.raise_for_status()
            data = resp.json()
        vs_id = str(data.get("id") or "").strip()
        if not vs_id:
            raise RuntimeError("StepFun vector_store 创建响应缺少 id 字段")
        return vs_id

    async def _upload_kb_file(self, api_base: str, api_key: str) -> str:
        """POST /files (purpose=retrieval) → 返回 file_id。"""
        url = f"{api_base}/files"
        if not is_safe_http_url(url, allow_local=False):
            raise UnsafeURLError(f"StepFun URL 被拒: {url}")
        content = _serialize_documents_to_jsonl()
        files = {"file": (_STEPFUN_FILE_NAME, content, "application/jsonl")}
        data = {"purpose": "retrieval"}
        headers = {"Authorization": f"Bearer {api_key}"}
        async with self._pinned_client(api_base) as client:
            resp = await client.post(url, headers=headers, data=data, files=files)
            resp.raise_for_status()
            payload = resp.json()
        file_id = str(payload.get("id") or "").strip()
        if not file_id:
            raise RuntimeError("StepFun files 上传响应缺少 id 字段")
        return file_id

    async def _attach_file(
        self,
        api_base: str,
        api_key: str,
        vector_store_id: str,
        file_id: str,
    ) -> None:
        """POST /vector_stores/{id}/files 关联文件。"""
        url = f"{api_base}/vector_stores/{vector_store_id}/files"
        if not is_safe_http_url(url, allow_local=False):
            raise UnsafeURLError(f"StepFun URL 被拒: {url}")
        payload = {"file_ids": file_id}
        async with self._pinned_client(api_base) as client:
            resp = await client.post(url, headers=self._headers(), json=payload)
            resp.raise_for_status()

    async def _verify_vector_store(
        self,
        api_base: str,
        api_key: str,
        vector_store_id: str,
    ) -> None:
        """GET /vector_stores/{id} 轻量校验 ID 存在。失败时清空,等待下次重建。"""
        url = f"{api_base}/vector_stores/{vector_store_id}"
        if not is_safe_http_url(url, allow_local=False):
            raise UnsafeURLError(f"StepFun URL 被拒: {url}")
        async with self._pinned_client(api_base) as client:
            resp = await client.get(url, headers=self._headers())
            if resp.status_code == 404:
                raise RuntimeError(f"StepFun vector_store 不存在: id={vector_store_id}")
            resp.raise_for_status()


__all__ = ["StepFunRetrievalRAG"]
"""StepFun vector_stores 索引 HTTP 层：create / upload / attach / verify。

拆自 :mod:`...stepfun_backend`。只做 StepFun 托管索引的建库/上传/挂载/校验
请求，不接触协议面（``query`` / ``build_retrieval_tool``）。出站一律走
:func:`make_pinned_async_client`（DNS pin），不做裸 ``httpx.AsyncClient``。
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from shared.core.security import (
    UnsafeURLError,
    is_safe_http_url,
    make_pinned_async_client,
    redact_api_key,
)
from shared.config import get_settings

logger = logging.getLogger(__name__)

_STEPFUN_FILE_NAME = "company_kb.jsonl"
_STEPFUN_VS_NAME = "company_kb"
_STEPFUN_REQUEST_TIMEOUT = 30.0


class StepFunIndexHttp:
    """StepFun 托管索引的 HTTP 客户端（无状态，仅请求编排）。"""

    def __init__(self, llm: Any, settings: Any):
        self._llm = llm
        self._settings = settings

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._llm.api_key}",
            "Content-Type": "application/json",
        }

    def _pinned_client(self, api_base: str) -> httpx.AsyncClient:
        """与 LLM client 一致：出站 DNS pin，缓解重绑定 TOCTOU。"""
        return make_pinned_async_client(
            api_base,
            allow_local=False,
            require_https=bool(get_settings().is_prod),
            timeout=_STEPFUN_REQUEST_TIMEOUT,
        )

    async def create_vector_store(self, api_base: str, api_key: str) -> str:
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

    async def upload_kb_file(
        self,
        api_base: str,
        api_key: str,
        content: bytes,
    ) -> str:
        """POST /files (purpose=retrieval) → 返回 file_id。"""
        url = f"{api_base}/files"
        if not is_safe_http_url(url, allow_local=False):
            raise UnsafeURLError(f"StepFun URL 被拒: {url}")
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

    async def attach_file(
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

    async def verify_vector_store(
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

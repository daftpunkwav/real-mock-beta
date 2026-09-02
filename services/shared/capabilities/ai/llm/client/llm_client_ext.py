"""LLMClient 出站探测与 embeddings：``test_connection`` / ``embed``。

运行期单向依赖：``llm_client`` 在类定义后 import 本模块；本模块仅 TYPE_CHECKING 引用 ``LLMClient``。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import httpx

from shared.config import get_settings
from shared.core.security import UnsafeURLError, is_safe_http_url

from .base import _is_local_allowed, _require_https
from .openai_transport import embed_texts

if TYPE_CHECKING:
    from .llm_client import LLMClient


async def test_connection(client: "LLMClient") -> tuple[bool, str]:
    """测试 API 连通性（轻量探测，不泄露 key）。"""
    try:
        reply = await client.chat(
            [
                {
                    "role": "system",
                    "content": "只用纯文字回复，禁止任何 emoji 表情符号。",
                },
                {"role": "user", "content": "请回复：连接成功"},
            ],
            temperature=0,
        )
        return True, reply[:100]
    except httpx.HTTPStatusError as e:
        return False, f"HTTP {e.response.status_code}: {e.response.text[:200]}"
    except Exception as e:
        return False, str(e)


async def embed(
    client: "LLMClient",
    texts: list[str],
    *,
    model: str | None = None,
) -> list[list[float]]:
    """调用 OpenAI 兼容 /embeddings 端点，返回每段文本的向量。"""
    base = get_settings().effective_embeddings_base
    if not is_safe_http_url(base, allow_local=_is_local_allowed(), require_https=_require_https()):
        raise UnsafeURLError(f"Embeddings api_base 不安全: {base}")
    return await embed_texts(
        texts=texts,
        model=model,
        api_base=client.api_base,
        api_key=client.api_key,
    )


__all__ = ["embed", "test_connection"]
